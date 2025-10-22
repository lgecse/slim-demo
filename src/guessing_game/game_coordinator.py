"""
Game Coordinator - Manages the guessing game flow and rules.

The coordinator acts as the game master, managing turns, tracking questions,
and determining when the game ends.
"""

import asyncio
import json
import datetime
from typing import Dict, List, Optional
import slim_bindings # type: ignore
from .logging_config import setup_logger

logger = setup_logger(__name__)  # type: ignore

class GameState:
    """Tracks the current state of the guessing game."""
    
    def __init__(self, max_questions: int = 20, max_guesses_per_player: int = 3):
        self.max_questions = max_questions
        self.max_guesses_per_player = max_guesses_per_player
        self.questions_asked = 0
        self.player_guesses = {}  # Track guesses per player: {"Bob": 2, "Carol": 1, ...}
        self.current_turn = 0  # Which guesser's turn (0, 1, 2)
        self.game_active = False
        self.thinker_ready = False
        self.thinker_game_ready = False
        self.guessers = []  # List of guesser agent names
        self.guessers_game_ready = []  # List of guessers ready to play
        self.thinker = None
        self.game_log = []  # History of questions and answers
        self.invitations_sent = False  # Track if invitations have been sent
        
    def add_question(self, guesser: str, question: str, answer: str):
        """Add a question/answer pair to the game log."""
        self.questions_asked += 1
        self.game_log.append({
            'type': 'question',
            'turn': self.questions_asked,
            'guesser': guesser,
            'question': question,
            'answer': answer
        })
        
    def add_guess(self, guesser: str, guess: str, correct: bool):
        """Add a final guess to the game log."""
        # Extract simple name for tracking
        simple_name = guesser.split('-')[-1].split('/')[0].split(' ')[0] if '-' in guesser else guesser
        
        # Track guesses per player
        self.player_guesses[simple_name] = self.player_guesses.get(simple_name, 0) + 1
        
        self.game_log.append({
            'type': 'guess',
            'guesser': guesser,
            'guess': guess,
            'correct': correct
        })
        
    def is_game_over(self) -> bool:
        """Check if the game should end."""
        # Game ends if: max questions reached, someone won, or all players used all guesses
        correct_guess = any(entry.get('correct', False) for entry in self.game_log if entry['type'] == 'guess')
        all_players_exhausted = (len(self.player_guesses) > 0 and 
                                all(guesses >= self.max_guesses_per_player 
                                    for guesses in self.player_guesses.values()))
        
        return (self.questions_asked >= self.max_questions or 
                correct_guess or 
                all_players_exhausted)
                
    def can_player_guess(self, guesser: str) -> bool:
        """Check if a player can still make guesses."""
        simple_name = guesser.split('-')[-1].split('/')[0].split(' ')[0] if '-' in guesser else guesser
        current_guesses = self.player_guesses.get(simple_name, 0)
        return current_guesses < self.max_guesses_per_player
        
    def get_current_guesser(self) -> Optional[str]:
        """Get the name of the current guesser whose turn it is."""
        if not self.guessers:
            return None
        return self.guessers[self.current_turn % len(self.guessers)]
        
    def next_turn(self):
        """Advance to the next guesser's turn."""
        self.current_turn += 1


class GameCoordinator:
    """Coordinates the guessing game between agents."""
    
    def __init__(self, channel_name: str, max_questions: int = 20, max_guesses_per_player: int = 3):
        self.channel_name = channel_name
        self.state = GameState(max_questions, max_guesses_per_player)
        self.slim_app = None
        self.session = None  # Group session for public messages
        self.running = True
    
    def get_simple_name(self, full_id: str) -> str:
        """Extract simple agent name from SLIM ID for readable logs."""
        # SLIM IDs look like: "6bc9fa09.../1e73ba0867bb4909/426aede976b69d1e (classroom/guesser-Bob/426aede976b69d1e)"
        # or just: "guesser-Bob" or "thinker-Alice"
        
        if '(' in full_id and ')' in full_id:
            paren_content = full_id.split('(')[1].split(')')[0]
            parts = paren_content.split('/')
            if len(parts) >= 3:
                agent_part = parts[2]
                if '-' in agent_part:
                    return agent_part.split('-')[1]
        
        if 'guesser-' in full_id:
            return full_id.split('guesser-')[1].split('/')[0].split(' ')[0]
        elif 'thinker-' in full_id:
            return full_id.split('thinker-')[1].split('/')[0].split(' ')[0]
        
        return full_id[:10] + "..." if len(full_id) > 10 else full_id
        
    async def connect_to_slim(self, slim_config: dict, shared_secret: str):
        """Connect to the SLIM messaging platform."""
        # Create identity for the coordinator
        provider = slim_bindings.PyIdentityProvider.SharedSecret(
            identity="game-coordinator", 
            shared_secret=shared_secret
        )
        verifier = slim_bindings.PyIdentityVerifier.SharedSecret(
            identity="game-coordinator",
            shared_secret=shared_secret
        )
        
        await slim_bindings.init_tracing({"log_level": "info"})
        # Create local identity
        local_name = slim_bindings.PyName("school", "classroom", "coordinator")
        self.slim_app = await slim_bindings.Slim.new(local_name, provider, verifier)
        
        # Connect to SLIM service
        await self.slim_app.connect(slim_config)
        logger.info(f"Game Coordinator connected! ID: {self.slim_app.id_str}")
        
        # Create group session for the game
        channel = slim_bindings.PyName("school", "classroom", "guessing-game")
        self.session = await self.slim_app.create_session(
            slim_bindings.PySessionConfiguration.Group(
                channel_name=channel,
                max_retries=5,
                timeout=datetime.timedelta(seconds=10),
                mls_enabled=True
            )
        )
        logger.info(f"Game channel created: {channel}")
        
        # Wait for all agents to initialize and start listening (Translator needs extra time for LLM init)
        logger.debug("Waiting 10 seconds for all agents to be ready to receive invitations...")
        await asyncio.sleep(10)
        
        # Invite all expected agents to the game
        expected_agents = [
            "school/classroom/thinker-Alice",
            "school/classroom/guesser-Bob", 
            "school/classroom/guesser-Carol",
            "school/classroom/guesser-Dave"
        ]
        
        # Optional observers (invited but not required for game to start)
        optional_observers = [
            "school/classroom/translator-Travis"
        ]
        
        for agent_id in expected_agents:
            try:
                agent_name = slim_bindings.PyName("school", "classroom", agent_id.split("/")[-1])
                await self.slim_app.set_route(agent_name)
                await self.session.invite(agent_name)
                logger.info(f"Invited {agent_id} to the game")
            except Exception as e:
                logger.warning(f"  Could not invite {agent_id}: {e}")
        
        # Invite optional observers
        for agent_id in optional_observers:
            try:
                agent_name = slim_bindings.PyName("school", "classroom", agent_id.split("/")[-1])
                await self.slim_app.set_route(agent_name)
                await self.session.invite(agent_name)
                logger.info(f"Invited optional observer {agent_id}")
            except Exception as e:
                logger.warning(f"  Could not invite optional observer {agent_id}: {e}")
        
        await asyncio.sleep(5)

        logger.info("All agents invited to the game session")
        
    async def broadcast_message(self, msg_type: str, data: dict):
        """Send a message to all agents in the game."""
        message = {
            'type': msg_type,
            'timestamp': datetime.datetime.now().isoformat(),
            'data': data
        }
        await self.session.publish(json.dumps(message).encode())
        
    async def handle_agent_message(self, source_name: str, payload: bytes):
        """Process messages from game agents."""
        try:
            message = json.loads(payload.decode())
            msg_type = message.get('type')
            logger.debug(f"Message type: {message.get('type')}")
            
            if msg_type == 'agent_ready':
                await self.handle_agent_ready(source_name, message['data'])
            elif msg_type == 'game_ready':
                await self.handle_game_ready(source_name, message['data'])
            elif msg_type == 'question':
                await self.handle_question(source_name, message['data'])
            elif msg_type == 'answer':
                await self.handle_answer(source_name, message['data'])
            elif msg_type == 'guess':
                await self.handle_guess(source_name, message['data'])
            elif msg_type == 'guess_result':
                await self.handle_guess_result(source_name, message['data'])
            
            logger.debug("Message handled successfully")
        except Exception as e:
            logger.error(f"Error processing message from {source_name}: {e}")
    
    async def send_invitations(self):
        """Send game invitations to all agents."""
        await self.broadcast_message('game_invitation', {
            'max_questions': self.state.max_questions,
            'max_guesses_per_player': self.state.max_guesses_per_player,
            'rules': {
                'target_audience': ' children',
                'principle': 'Choose objects from daily life that every child would recognize',
                'requirement': 'Any object familiar to children - be creative and varied!',
                'language': 'The game will be played in English - objects, questions, and answers should all be in English'
            }
        })
    
    async def handle_game_ready(self, source_name: str, data: dict):
        """Handle agents signaling they're ready to play."""
        agent_role = data.get('role')
        agent_name = data.get('name')
        
        if agent_role == 'thinker':
            logger.info(f"Thinker {agent_name} is ready with chosen object!")
            self.state.thinker_game_ready = True
        elif agent_role == 'guesser':
            logger.info(f"Guesser {agent_name} is ready to play!")
            if agent_name not in self.state.guessers_game_ready:
                self.state.guessers_game_ready.append(agent_name)
        
        # Start game if all agents are ready
        if (self.state.thinker_game_ready and 
            len(self.state.guessers_game_ready) >= 3):
            logger.info("All agents are ready - starting the game!")
            self.state.game_active = True
            await self.next_turn()
            
    async def handle_agent_ready(self, agent_name: str, data: dict):
        """Handle agent registration."""
        role = data.get('role')
        simple_name = data.get('name')  # Use the simple name provided by the agent
        
        if role == 'thinker':
            self.state.thinker = f"thinker-{simple_name}"
            self.state.thinker_ready = True
            logger.info(f"Thinker ready: {simple_name}")
            
        elif role == 'guesser':
            guesser_name = f"guesser-{simple_name}"
            if guesser_name not in self.state.guessers:
                self.state.guessers.append(guesser_name)
                logger.info(f"Guesser joined: {simple_name} (Total: {len(self.state.guessers)})")
                
        # Send invitations if we have all players connected and haven't sent them yet
        if (self.state.thinker_ready and len(self.state.guessers) >= 3 and 
            not self.state.invitations_sent):
            logger.info("All agents connected - sending game invitations...")
            self.state.invitations_sent = True
            await self.send_invitations()
            
    async def start_game(self):
        """Begin the guessing game."""
        if self.state.game_active:
            return
            
        self.state.game_active = True
        logger.info("Starting the guessing game!")
        
        # Tell thinker to choose an object
        await self.broadcast_message('game_start', {
            'thinker': self.state.thinker,
            'guessers': self.state.guessers,
            'max_questions': self.state.max_questions,
            'max_guesses_per_player': self.state.max_guesses_per_player
        })
        
    async def next_turn(self):
        """Start the next guesser's turn."""
        logger.debug(f"next_turn() called - game_active={self.state.game_active}, questions={self.state.questions_asked}/{self.state.max_questions}")
        
        if self.state.is_game_over():
            logger.debug("Game is over, calling end_game()")
            await self.end_game()
            return
            
        current_guesser = self.state.get_current_guesser()
        if current_guesser:
            logger.debug(f"Sending 'your_turn' to {current_guesser}")
            logger.debug(f"  Questions remaining: {self.state.max_questions - self.state.questions_asked}")
            logger.debug(f"  Player guesses: {self.state.player_guesses}")
            
            await self.broadcast_message('your_turn', {
                'guesser': current_guesser,
                'questions_remaining': self.state.max_questions - self.state.questions_asked,
                'player_guesses': self.state.player_guesses,
                'max_guesses_per_player': self.state.max_guesses_per_player,
                'game_log': self.state.game_log[-5:]  # Last 5 entries for context
            })
            
            logger.debug(f"'your_turn' message broadcast complete")
            simple_name = self.get_simple_name(current_guesser)
            logger.info(f"{simple_name}'s turn (Question #{self.state.questions_asked + 1})")
        else:
            logger.warning(f"No current guesser! Current turn: {self.state.current_turn}, Guessers: {self.state.guessers}")
            
    async def handle_question(self, guesser: str, data: dict):
        """Forward question from guesser to thinker."""
        if not self.state.game_active:
            logger.debug(f"Ignoring question from {guesser} - game not active")
            return

        current_guesser = self.state.get_current_guesser()
        
        question = data.get('question', '')
        simple_name = self.get_simple_name(guesser)
        logger.debug(f"Received question from {guesser}: '{question}'")
        logger.info(f"{simple_name}: {question}")
        
        await self.broadcast_message('question_for_thinker', {
            'guesser': guesser,
            'question': question
        })
        
    async def handle_answer(self, thinker: str, data: dict):
        """Process answer from thinker and advance game."""
        if not self.state.game_active:
            return
            
        question = data.get('question', '')
        answer = data.get('answer', '')
        guesser = data.get('guesser', '')
        
        simple_name = self.get_simple_name(thinker)
        logger.info(f"{simple_name}: {answer}")
        
        # Record the Q&A
        self.state.add_question(guesser, question, answer)
        
        # Broadcast the answer
        await self.broadcast_message('answer_from_thinker', {
            'guesser': guesser,
            'question': question,
            'answer': answer,
            'turn_number': self.state.questions_asked
        })
        
        # Check if game should end or continue
        if self.state.is_game_over():
            await self.end_game()
        else:
            self.state.next_turn()
            await asyncio.sleep(1)
            asyncio.create_task(self.next_turn())
            
    async def handle_guess(self, guesser: str, data: dict):
        """Forward final guess to thinker for verification."""
        if not self.state.game_active:
            return
            
        guess = data.get('guess', '')
        simple_name = self.get_simple_name(guesser)
        logger.info(f"{simple_name}: {guess}")
        
        await self.broadcast_message('guess_for_thinker', {
            'guesser': guesser,
            'guess': guess
        })
        
    async def handle_guess_result(self, thinker: str, data: dict):
        """Process guess result and potentially end game."""
        if not self.state.game_active:
            return
            
        guesser = data.get('guesser', '')
        guess = data.get('guess', '')
        correct = data.get('correct', False)
        actual_object = data.get('actual_object', None)
        
        simple_name = self.get_simple_name(guesser)
        result = " CORRECT!" if correct else " wrong"
        logger.info(f"{simple_name} guessed '{guess}' - {result}")
        
        self.state.add_guess(guesser, guess, correct)
        
        broadcast_data = {
            'guesser': guesser,
            'guess': guess,
            'correct': correct
        }
        
        if correct and actual_object:
            broadcast_data['actual_object'] = actual_object
        
        await self.broadcast_message('guess_result', broadcast_data)
        
        if correct or self.state.is_game_over():
            await self.end_game(winner=guesser if correct else None, actual_object=actual_object if actual_object else None)
        else:
            logger.info(f"Game continues after wrong guess...")
            self.state.next_turn()
            await asyncio.sleep(1)
            await self.next_turn()
        
    async def end_game(self, winner: str = None, actual_object: str = None):
        """End the current game and show results."""
        self.state.game_active = False
        
        if winner:
            logger.info(f"Game Over! {winner} wins!")
            result = f"{winner} correctly guessed the object!"
        else:
            logger.info("Game Over! No one guessed correctly.")
            result = "Time's up! No one guessed the object."
            
        game_over_data = {
            'winner': winner,
            'result': result,
            'questions_asked': self.state.questions_asked,
            'total_guesses_made': sum(self.state.player_guesses.values()),
            'player_guesses': self.state.player_guesses,
            'game_log': self.state.game_log
        }
        
        if actual_object:
            game_over_data['actual_object'] = actual_object
            
        await self.broadcast_message('game_over', game_over_data)
        
        logger.info("Game complete! All agents can now exit.")
        logger.info("To play again, restart the pods with: task game:restart")
        
        self.running = False
        
    async def start_new_game(self):
        """Reset state and start a new game round."""
        logger.info("Starting a new game round...")
        
        current_thinker = self.state.thinker
        current_guessers = self.state.guessers.copy() if self.state.guessers else []
        current_thinker_ready = self.state.thinker_ready
        
        self.state = GameState(self.state.max_questions, self.state.max_guesses_per_player)
        
        self.state.thinker = current_thinker
        self.state.guessers = current_guessers
        self.state.thinker_ready = current_thinker_ready
        
        logger.debug(f"Restored agents - Thinker: {current_thinker}, Guessers: {current_guessers}")
        
        await asyncio.sleep(2)
        await self.start_game()
        
    async def run(self):
        """Main game loop."""
        logger.info("Game Coordinator is running...")
        logger.info("Waiting for agents to join...")
        
        self.running = True
        
        while self.running:
            try:
                logger.debug("Waiting for message...")
                ctx, payload = await self.session.get_message()
                logger.debug("Got message!!")
                await self.handle_agent_message(str(ctx.source_name), payload)
            except Exception as e:
                if self.running:
                    logger.error(f"Error in game loop: {e}")
                    await asyncio.sleep(1)
                else:
                    break
        
        logger.info("Coordinator shutting down after game completion.")


def coordinator_main(slim_config_json: str, shared_secret: str, game_channel: str, 
                    max_questions: int, max_guesses: int):
    """Main entry point for the game coordinator."""
    
    async def run_coordinator():
        coordinator = GameCoordinator(game_channel, max_questions, max_guesses)
        slim_config = json.loads(slim_config_json)
        
        await coordinator.connect_to_slim(slim_config, shared_secret)
        await coordinator.run()
        
    try:
        asyncio.run(run_coordinator())
    except KeyboardInterrupt:
        logger.info("Game Coordinator stopped by user.")
