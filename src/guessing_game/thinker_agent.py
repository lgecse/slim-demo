"""
Thinker Agent - Thinks of objects and answers yes/no questions using LLM intelligence.

The thinker agent uses LLM to choose creative objects and intelligently
answer questions about their properties.
"""

import asyncio
import json
import datetime
import slim_bindings
from .llm_agent import LLMThinkerAgent


class ThinkerAgent:
    """Agent that thinks of objects and answers questions about them using LLM intelligence."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.current_object = None
        self.llm_agent = LLMThinkerAgent()
        self.slim_app = None
        self.session = None  # Public group session
        self.secret_session = None  # Private 1:1 session with Travis (observer) for secrets
        
    async def connect_to_slim(self, slim_config: dict, shared_secret: str):
        """Connect to the SLIM messaging platform."""
        # Create identity for this thinker agent
        provider = slim_bindings.PyIdentityProvider.SharedSecret(
            identity=f"thinker-{self.agent_name}",
            shared_secret=shared_secret
        )
        verifier = slim_bindings.PyIdentityVerifier.SharedSecret(
            identity=f"thinker-{self.agent_name}",
            shared_secret=shared_secret
        )
        
        # Create local identity
        local_name = slim_bindings.PyName("school", "classroom", f"thinker-{self.agent_name}")
        self.slim_app = await slim_bindings.Slim.new(local_name, provider, verifier)
        
        # Connect to SLIM service
        await self.slim_app.connect(slim_config)
        print(f"Thinker Agent '{self.agent_name}' connected! ID: {self.slim_app.id_str}")
        
        # Wait for game session to exist, then join it
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
        
    async def choose_new_object(self):
        """Use local LLM to choose a new object to think about."""
        object_name = await self.llm_agent.choose_object()
        self.current_object = {"name": object_name}
        print(f"I'm thinking of: {object_name}")
        print(f"(Shh! Don't tell the guessers!)")
        
        # Send the secret object to Travis (observer) via our secure 1:1 session
        await self.send_secret_to_observer(object_name)
    
    async def send_secret_to_observer(self, object_name: str):
        """Send the secret object to Travis (observer) via secure 1:1 session."""
        # Wait for secret session to be established
        max_wait = 100  # 10 seconds
        wait_count = 0
        while not self.secret_session and wait_count < max_wait:
            await asyncio.sleep(0.1)
            wait_count += 1
        
        if not self.secret_session:
            print("WARNING: Secret session not established, cannot send secret securely!")
            return
        
        message = {
            'type': 'secret_object',
            'timestamp': datetime.datetime.now().isoformat(),
            'data': {'object': object_name}
        }
        
        await self.secret_session.publish(json.dumps(message).encode())
        print(f"Sent secret object '{object_name}' to Travis (observer) via secure 1:1 session")
        
    async def answer_question(self, question: str) -> str:
        """Use local LLM to intelligently answer yes/no questions about the current object."""
        if not self.current_object:
            return "I haven't chosen an object yet!"
        
        return await self.llm_agent.answer_question(question)
    
        
    async def check_guess(self, guess: str) -> bool:
        """Use local LLM to intelligently check if a guess matches the current object."""
        if not self.current_object:
            return False
        
        return await self.llm_agent.check_guess(guess)
        
    async def handle_message(self, message: dict):
        """Process messages from the game coordinator."""
        msg_type = message.get('type')
        data = message.get('data', {})
        
        if msg_type == 'game_invitation':
            rules = data.get('rules', {})
            target_audience = rules.get('target_audience', 'children')
            language_rule = rules.get('language', 'Game will be in English')
            print(f"Received game invitation for {target_audience} - choosing child-friendly object...")
            print(f"{language_rule}")
            await self.choose_new_object()
            await self.send_game_ready()
            
        elif msg_type == 'question_for_thinker':
            question = data.get('question', '')
            guesser = data.get('guesser', '')
            
            print(f"Question from {guesser}: '{question}'")
            answer = await self.answer_question(question)
            print(f"My answer: '{answer}'")
            
            await self.send_message('answer', {
                'question': question,
                'answer': answer,
                'guesser': guesser
            })
            
        elif msg_type == 'guess_for_thinker':
            guess = data.get('guess', '')
            guesser = data.get('guesser', '')
            
            print(f"Guess from {guesser}: '{guess}'")
            correct = await self.check_guess(guess)
            
            if correct:
                print(f"Correct! The object was '{self.current_object['name']}'")
            else:
                print(f"Wrong! It's not '{guess}', it's '{self.current_object['name']}'")
            
            # Send guess result WITHOUT actual_object
            # Coordinator already knows the object from our secure 1:1 session transmission
            result_data = {
                'guesser': guesser,
                'guess': guess,
                'correct': correct
            }
            
            # Note: We don't include actual_object here because:
            # 1. Coordinator already received it securely at game start
            # 2. This prevents leaking the secret on the public channel
            
            await self.send_message('guess_result', result_data)
            
        elif msg_type == 'game_over':
            winner = data.get('winner')
            if winner:
                print(f"Game over! {winner} won by guessing '{self.current_object['name']}'!")
            else:
                print(f"Game over! No one guessed '{self.current_object['name']}'.")
            
            # Signal to exit after game over
            self.running = False
            print("Thinker agent exiting after game completion.")
            
    async def send_ready(self):
        """Tell the coordinator that this agent is connected and ready."""
        await self.send_message('agent_ready', {
            'role': 'thinker',
            'name': self.agent_name
        })
        
    async def send_game_ready(self):
        """Tell everyone that the thinker has chosen an object and is ready to play."""
        await self.send_message('game_ready', {
            'role': 'thinker',
            'name': self.agent_name,
            'object_chosen': True
        })
        print("Thinker ready with object - game can begin!")
        
    async def run(self):
        """Main agent loop - listens on both public and secret sessions."""
        print(f"Thinker Agent '{self.agent_name}' is connected and waiting for game start...")
        
        # Send initial ready signal (connection ready)
        await self.send_ready()
        self.running = True
        
        async def listen_public_session():
            """Listen for messages on the public group session."""
            while self.running:
                try:
                    # Use timeout to allow checking running flag periodically
                    try:
                        ctx, payload = await asyncio.wait_for(self.session.get_message(), timeout=1.0)
                        message = json.loads(payload.decode())
                        await self.handle_message(message)
                    except asyncio.TimeoutError:
                        # Timeout is normal - just continue to check running flag
                        continue
                except Exception as e:
                    if self.running:
                        print(f"Error in public session: {e}")
                        await asyncio.sleep(1)
                    else:
                        break
        
        async def listen_secret_session():
            """Wait for and listen on the secret 1:1 session with Travis (observer)."""
            try:
                # Wait for secret session invitation
                print("Waiting for secret 1:1 session invitation from Travis (observer)...")
                self.secret_session = await self.slim_app.listen_for_session()
                print(f"Joined secret 1:1 session with Travis (observer)!")
                
                # Now listen for any messages on the secret session (though we mainly send, not receive)
                while self.running:
                    try:
                        # Use timeout to allow checking running flag periodically
                        try:
                            ctx, payload = await asyncio.wait_for(self.secret_session.get_message(), timeout=1.0)
                            message = json.loads(payload.decode())
                            # Handle any secret messages if needed
                            pass
                        except asyncio.TimeoutError:
                            # Timeout is normal - just continue to check running flag
                            continue
                    except Exception as e:
                        if self.running:
                            print(f"Error in secret session: {e}")
                            await asyncio.sleep(1)
                        else:
                            break
            except Exception as e:
                print(f"Failed to join secret session: {e}")
        
        # Listen on both sessions concurrently
        try:
            await asyncio.gather(
                listen_public_session(),
                listen_secret_session()
            )
        except Exception as e:
            print(f"Error in main loop: {e}")
        
        print(f"Thinker '{self.agent_name}' has exited cleanly.")


def thinker_main(slim_config_json: str, shared_secret: str, game_channel: str, 
                agent_name: str):
    """Main entry point for a thinker agent."""
    
    async def run_thinker():
        agent = ThinkerAgent(agent_name)
        
        # Parse SLIM config
        slim_config = json.loads(slim_config_json)
        
        await agent.connect_to_slim(slim_config, shared_secret)
        await agent.run()
        
    try:
        asyncio.run(run_thinker())
    except KeyboardInterrupt:
        print(f"Thinker Agent '{agent_name}' stopped by user.")
