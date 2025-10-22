"""
Guesser Agent - Asks questions and tries to guess the object using LLM intelligence.

The guesser agents use LLM-powered strategies to ask intelligent questions and
make educated guesses about what the thinker is thinking of.
"""

import asyncio
import json
import datetime
from typing import List, Dict
import slim_bindings  # type: ignore
from .llm_agent import LLMGuesserAgent
from .logging_config import setup_logger

logger = setup_logger(__name__)


class GuesserAgent:
    """Agent that asks questions and tries to guess objects using LLM intelligence."""
    
    def __init__(self, agent_name: str, strategy_name: str = "random"):
        self.agent_name = agent_name
        self.strategy_name = strategy_name
        self.llm_agent = LLMGuesserAgent(agent_name, strategy_name)
        self.slim_app = None
        self.session = None
        self.my_turn = False
        self.turn_task = None  # Track background turn processing task
            
    async def connect_to_slim(self, slim_config: dict, shared_secret: str):
        """Connect to the SLIM messaging platform."""
        provider = slim_bindings.PyIdentityProvider.SharedSecret(
            identity=f"guesser-{self.agent_name}",
            shared_secret=shared_secret
        )
        verifier = slim_bindings.PyIdentityVerifier.SharedSecret(
            identity=f"guesser-{self.agent_name}",
            shared_secret=shared_secret
        )
        
        await slim_bindings.init_tracing({"log_level": "info"})
        local_name = slim_bindings.PyName("school", "classroom", f"guesser-{self.agent_name}")
        self.slim_app = await slim_bindings.Slim.new(local_name, provider, verifier)
        
        await self.slim_app.connect(slim_config)
        logger.info(f"Guesser Agent '{self.agent_name}' connected! ID: {self.slim_app.id_str}")
        
        logger.debug("Looking for game session...")
        self.session = await self.slim_app.listen_for_session()
        logger.info(f"Joined game session!")
        
    async def send_message(self, msg_type: str, data: dict):
        """Send a message to the game coordinator."""
        message = {
            'type': msg_type,
            'timestamp': datetime.datetime.now().isoformat(),
            'data': data
        }
        await self.session.publish(json.dumps(message).encode())
        
    async def handle_message(self, message: dict):
        """Process messages from the game coordinator."""
        msg_type = message.get('type')
        data = message.get('data', {})
        
        logger.debug(f"handle_message called with type: {msg_type}")
        
        if msg_type == 'game_invitation':
            rules = data.get('rules', {})
            target_audience = rules.get('target_audience', 'children')
            requirement = rules.get('requirement', 'Objects familiar to children')
            language_rule = rules.get('language', 'Game will be in English')
            logger.info(f"Received game invitation for {target_audience}!")
            logger.debug(f"{requirement}")
            logger.debug(f"{language_rule}")
            await self.send_game_ready()
        
        if msg_type == 'game_start':
            logger.info("Game is starting!")
            await self.send_ready()
            
        elif msg_type == 'your_turn':
            current_guesser = data.get('guesser')
            my_name = f"guesser-{self.agent_name}"
            questions_remaining = data.get('questions_remaining', 0)
            
            logger.debug(f"Received 'your_turn' message")
            logger.debug(f"  Current guesser in message: {current_guesser}")
            logger.debug(f"  My name: {my_name}")
            logger.debug(f"  Questions remaining: {questions_remaining}")
            logger.debug(f"  Match: {current_guesser == my_name}")
            
            if current_guesser == my_name:
                logger.debug(f"It's MY turn! Processing in background task...")
                # Cancel any existing turn task (shouldn't happen, but be safe)
                if self.turn_task and not self.turn_task.done():
                    logger.warning("Previous turn task still running, cancelling it")
                    self.turn_task.cancel()
                
                # Process turn in background so message loop can continue
                self.turn_task = asyncio.create_task(
                    self._process_my_turn(questions_remaining, data.get('game_log', []))
                )
            else:
                logger.debug(f"Not my turn, ignoring")
            
        elif msg_type == 'answer_from_thinker':
            guesser = data.get('guesser')
            question = data.get('question')
            answer = data.get('answer')
            turn_number = data.get('turn_number')
            
            if guesser == f"guesser-{self.agent_name}":
                logger.info(f"My question '{question}' was answered: '{answer}'")
            else:
                logger.info(f"{guesser} asked '{question}' and got '{answer}'")
                
        elif msg_type == 'guess_result':
            guesser = data.get('guesser')
            guess = data.get('guess')
            correct = data.get('correct')
            actual_object = data.get('actual_object')
            
            # Add guess result to game history for all agents to learn from
            guess_entry = {
                'type': 'guess',
                'guesser': guesser,
                'guess': guess,
                'correct': correct
            }
            self.llm_agent.game_history.append(guess_entry)
            
            if guesser == f"guesser-{self.agent_name}":
                if correct:
                    logger.info(f"YES! I guessed correctly! It was '{actual_object}'!")
                else:
                    logger.info(f"No, my guess '{guess}' was wrong. It was '{actual_object}'.")
            else:
                if correct:
                    logger.info(f"{guesser} won! They guessed '{actual_object}' correctly!")
                else:
                    logger.info(f"{guesser} guessed '{guess}' but it was wrong.")
                    
        elif msg_type == 'game_over':
            winner = data.get('winner')
            result = data.get('result')
            questions_asked = data.get('questions_asked')
            actual_object = data.get('actual_object', 'unknown')
            
            logger.info(f"Game Over! {result}")
            logger.info(f"The object was: {actual_object}")
            logger.info(f"Total questions asked: {questions_asked}")
            
            if winner == f"guesser-{self.agent_name}":
                logger.info("I won this round!")
            elif winner:
                logger.info(f"{winner} won this round. Good job!")
            else:
                logger.info("No one won this round.")
            
            # Signal to exit after game over
            self.running = False
            logger.info("Guesser agent exiting after game completion.")
    
    async def _process_my_turn(self, questions_remaining: int, game_log: List[Dict]):
        """Process this agent's turn in a background task to avoid blocking message loop."""
        try:
            self.my_turn = True
            logger.info(f"It's my turn! ({questions_remaining} questions remaining)")
            
            self.llm_agent.update_game_history(game_log)
            
            try:
                should_guess = await asyncio.wait_for(self.llm_agent.should_make_guess(), timeout=10.0) or questions_remaining <= 2
            except asyncio.TimeoutError:
                logger.error("LLM timeout while deciding action! Asking question as fallback.")
                should_guess = False
            
            logger.debug(f"Decision: {'GUESS' if should_guess else 'ASK QUESTION'}")
            
            if should_guess:
                await self.make_guess(game_log)
            else:
                await self.ask_question(game_log)
                
            self.my_turn = False
            logger.debug(f"Turn complete")
        except asyncio.CancelledError:
            logger.warning("Turn processing was cancelled")
            self.my_turn = False
        except Exception as e:
            logger.error(f"Error processing turn: {e}")
            self.my_turn = False
                
    async def ask_question(self, game_log: List[Dict] = None):
        """Use LLM to ask an intelligent question about the object."""
        logger.debug(f"Calling LLM to generate question...")
        try:
            question = await asyncio.wait_for(self.llm_agent.ask_question(), timeout=30.0)
            logger.debug(f"LLM generated question: '{question}'")
            logger.info(f"I'm asking: '{question}'")
            
            logger.debug(f"Sending 'question' message to coordinator...")
            await self.send_message('question', {
                'question': question
            })
            logger.debug(f"Question sent")
        except asyncio.TimeoutError:
            logger.error("LLM timeout while generating question! Using fallback.")
            await self.send_message('question', {
                'question': "Is it something you can hold in your hand?"
            })
        
    async def make_guess(self, game_log: List[Dict] = None):
        """Use LLM to make an educated guess about the object."""
        try:
            guess = await asyncio.wait_for(self.llm_agent.make_guess(), timeout=30.0)
            logger.info(f"I'm guessing: '{guess}'")
            
            await self.send_message('guess', {
                'guess': guess
            })
        except asyncio.TimeoutError:
            logger.error("LLM timeout while generating guess! Using fallback.")
            await self.send_message('guess', {
                'guess': "ball"
            })
        
    async def send_ready(self):
        """Tell the coordinator that this agent is ready."""
        await self.send_message('agent_ready', {
            'role': 'guesser',
            'name': self.agent_name,
            'strategy': f"LLM-{self.strategy_name}"
        })
        
    async def send_game_ready(self):
        """Tell the coordinator that this agent is ready to play."""
        await self.send_message('game_ready', {
            'role': 'guesser',
            'name': self.agent_name
        })
        
    async def run(self):
        """Main agent loop."""
        logger.info(f"Guesser Agent '{self.agent_name}' is ready!")
        logger.info(f"Using LLM-powered {self.strategy_name} strategy")
        
        await self.send_ready()
        self.running = True
        
        while self.running:
            try:
                logger.debug("Waiting for message...")
                ctx, payload = await self.session.get_message()
                logger.debug("Got message!!")
                message = json.loads(payload.decode())
                logger.debug(f"Message type: {message.get('type')}")
                await self.handle_message(message)
                logger.debug("Message handled successfully")
            except Exception as e:
                if self.running:
                    logger.error(f"Error in agent loop: {e}")
                    await asyncio.sleep(1)
                else:
                    break
        
        logger.info(f"Guesser '{self.agent_name}' has exited cleanly.")


def guesser_main(slim_config_json: str, shared_secret: str, game_channel: str,
                agent_name: str, strategy: str):
    """Main entry point for a guesser agent."""
    
    async def run_guesser():
        agent = GuesserAgent(agent_name, strategy)
        
        # Parse SLIM config
        slim_config = json.loads(slim_config_json)
        
        await agent.connect_to_slim(slim_config, shared_secret)
        await agent.run()
        
    try:
        asyncio.run(run_guesser())
    except KeyboardInterrupt:
        logger.info(f"Guesser Agent '{agent_name}' stopped by user.")
