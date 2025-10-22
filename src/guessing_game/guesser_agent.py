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


class GuesserAgent:
    """Agent that asks questions and tries to guess objects using LLM intelligence."""
    
    def __init__(self, agent_name: str, strategy_name: str = "random"):
        self.agent_name = agent_name
        self.strategy_name = strategy_name
        self.llm_agent = LLMGuesserAgent(agent_name, strategy_name)
        self.slim_app = None
        self.session = None
        self.my_turn = False
            
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
        
        local_name = slim_bindings.PyName("classroom", f"guesser-{self.agent_name}")
        self.slim_app = await slim_bindings.Slim.new(local_name, provider, verifier)
        
        await self.slim_app.connect(slim_config)
        print(f"Guesser Agent '{self.agent_name}' connected! ID: {self.slim_app.id_str}")
        
        print("Looking for game session...")
        self.session = await self.slim_app.listen_for_session()
        print(f"Joined game session!")
        
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
        
        if msg_type == 'game_invitation':
            rules = data.get('rules', {})
            target_audience = rules.get('target_audience', 'children')
            requirement = rules.get('requirement', 'Objects familiar to children')
            language_rule = rules.get('language', 'Game will be in English')
            print(f"Received game invitation for {target_audience}!")
            print(f"{requirement}")
            print(f"{language_rule}")
            await self.send_game_ready()
        
        if msg_type == 'game_start':
            print("Game is starting!")
            await self.send_ready()
            
        elif msg_type == 'your_turn':
            current_guesser = data.get('guesser')
            my_name = f"guesser-{self.agent_name}"
            
            if current_guesser == my_name:
                self.my_turn = True
                game_log = data.get('game_log', [])
                questions_remaining = data.get('questions_remaining', 0)
                
                print(f"It's my turn! ({questions_remaining} questions remaining)")
                
                self.llm_agent.update_game_history(game_log)
                
                should_guess = await self.llm_agent.should_make_guess() or questions_remaining <= 2
                
                if should_guess:
                    await self.make_guess(game_log)
                else:
                    await self.ask_question(game_log)
                    
                self.my_turn = False
            
        elif msg_type == 'answer_from_thinker':
            guesser = data.get('guesser')
            question = data.get('question')
            answer = data.get('answer')
            turn_number = data.get('turn_number')
            
            if guesser == f"guesser-{self.agent_name}":
                print(f"My question '{question}' was answered: '{answer}'")
            else:
                print(f"{guesser} asked '{question}' and got '{answer}'")
                
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
                    print(f"YES! I guessed correctly! It was '{actual_object}'!")
                else:
                    print(f"No, my guess '{guess}' was wrong. It was '{actual_object}'.")
            else:
                if correct:
                    print(f"{guesser} won! They guessed '{actual_object}' correctly!")
                else:
                    print(f"{guesser} guessed '{guess}' but it was wrong.")
                    
        elif msg_type == 'game_over':
            winner = data.get('winner')
            result = data.get('result')
            questions_asked = data.get('questions_asked')
            actual_object = data.get('actual_object', 'unknown')
            
            print(f"Game Over! {result}")
            print(f"The object was: {actual_object}")
            print(f"Total questions asked: {questions_asked}")
            
            if winner == f"guesser-{self.agent_name}":
                print("I won this round!")
            elif winner:
                print(f"{winner} won this round. Good job!")
            else:
                print("No one won this round.")
            
            # Signal to exit after game over
            self.running = False
            print("Guesser agent exiting after game completion.")
                
    async def ask_question(self, game_log: List[Dict] = None):
        """Use LLM to ask an intelligent question about the object."""
        question = await self.llm_agent.ask_question()
        print(f"I'm asking: '{question}'")
        
        await self.send_message('question', {
            'question': question
        })
        
    async def make_guess(self, game_log: List[Dict] = None):
        """Use LLM to make an educated guess about the object."""
        guess = await self.llm_agent.make_guess()
        print(f"I'm guessing: '{guess}'")
        
        await self.send_message('guess', {
            'guess': guess
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
        print(f"Guesser Agent '{self.agent_name}' is ready!")
        print(f"Using LLM-powered {self.strategy_name} strategy")
        
        await self.send_ready()
        self.running = True
        
        while self.running:
            try:
                try:
                    ctx, payload = await asyncio.wait_for(self.session.get_message(), timeout=1.0)
                    message = json.loads(payload.decode())
                    await self.handle_message(message)
                except asyncio.TimeoutError:
                    continue
                
            except Exception as e:
                if self.running:
                    print(f"Error in agent loop: {e}")
                    await asyncio.sleep(1)
                else:
                    break
        
        print(f"Guesser '{self.agent_name}' has exited cleanly.")


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
        print(f"Guesser Agent '{agent_name}' stopped by user.")
