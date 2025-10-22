"""
Thinker Agent - Thinks of objects and answers yes/no questions using LLM intelligence.

The thinker agent uses LLM to choose creative objects and intelligently
answer questions about their properties.
"""

import asyncio
import json
import datetime
import logging
import slim_bindings  # type: ignore
from .llm_agent import LLMThinkerAgent
from .logging_config import setup_logger

logger = setup_logger(__name__)


class ThinkerAgent:
    """Agent that thinks of objects and answers questions about them using LLM intelligence."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.current_object = None
        self.llm_agent = LLMThinkerAgent()
        self.slim_app = None
        self.session = None  # Public group session
        self.secret_session = None  # Private 1:1 session with Travis (observer) for secrets
        self.running = True
        
    async def connect_to_slim(self, slim_config: dict, shared_secret: str):
        """Connect to the SLIM messaging platform."""
        # Provider: proves our identity
        provider = slim_bindings.PyIdentityProvider.SharedSecret(
            identity=f"thinker-{self.agent_name}",
            shared_secret=shared_secret
        )
        # Verifier: verifies ANY identity with this shared secret (for peer-to-peer)
        verifier = slim_bindings.PyIdentityVerifier.SharedSecret(
            identity="",  # Empty = accept any identity with the shared secret
            shared_secret=shared_secret
        )
        
        await slim_bindings.init_tracing({"log_level": "info"})
        local_name = slim_bindings.PyName("school", "classroom", f"thinker-{self.agent_name}")
        self.slim_app = await slim_bindings.Slim.new(local_name, provider, verifier)
        
        await self.slim_app.connect(slim_config)
        logger.info(f"Thinker Agent '{self.agent_name}' connected! ID: {self.slim_app.id_str}")
        
        # Join game session
        logger.debug("Looking for game session...")
        self.session = await self.slim_app.listen_for_session()
        logger.info(f"Joined game session!")
        
        # Create PointToPoint session with Travis (optional - game can run without him)
        logger.debug("Creating secret PointToPoint session with Travis...")
        
        try:
            travis_name = slim_bindings.PyName("school", "classroom", "translator-Travis")
            await self.slim_app.set_route(travis_name)
            
            self.secret_session = await self.slim_app.create_session(
                slim_bindings.PySessionConfiguration.PointToPoint(
                    peer_name=travis_name,
                    max_retries=3,
                    timeout=datetime.timedelta(seconds=5),
                    mls_enabled=True
                )
            )
            logger.info(f"✓ Created secret PointToPoint session with Travis!")
        except Exception as e:
            logger.warning(f"Note: Could not establish secret session with Travis (optional observer): {e}")
            logger.info("Continuing game without Travis...")
        
    async def send_message(self, msg_type: str, data: dict):
        """Send a message to the game coordinator."""
        message = {
            'type': msg_type,
            'timestamp': datetime.datetime.now().isoformat(),
            'data': data
        }
        await self.session.publish(json.dumps(message).encode())
        
    async def choose_new_object(self):
        """Use LLM to choose a new object to think about."""
        object_name = await self.llm_agent.choose_object()
        self.current_object = {"name": object_name}
        logger.info(f"I'm thinking of: {object_name}")
        logger.info(f"(Shh! Don't tell the guessers!)")
        
        await self.send_secret_to_observer(object_name)
    
    async def send_secret_to_observer(self, object_name: str):
        """Send the secret object to Travis (observer) via secure 1:1 session."""
        logger.debug(f"Attempting to send secret '{object_name}' to Travis...")
        logger.debug(f"Secret session status: {self.secret_session is not None}")
        
        max_wait = 200  # 20 seconds
        wait_count = 0
        while not self.secret_session and wait_count < max_wait:
            if wait_count % 10 == 0:  # Log every second
                logger.debug(f"Waiting for secret session... ({wait_count/10:.0f}s)")
            await asyncio.sleep(0.1)
            wait_count += 1
        
        if not self.secret_session:
            logger.warning(f"WARNING: Secret session not established after {max_wait/10}s, cannot send secret securely!")
            return
        
        message = {
            'type': 'secret_object',
            'timestamp': datetime.datetime.now().isoformat(),
            'data': {'object': object_name}
        }
        
        await self.secret_session.publish(json.dumps(message).encode())
        logger.info(f"✓ Sent secret object '{object_name}' to Travis (observer) via secure 1:1 session")
        
    async def answer_question(self, question: str) -> str:
        """Use LLM to intelligently answer yes/no questions about the current object."""
        if not self.current_object:
            return "I haven't chosen an object yet!"
        
        return await self.llm_agent.answer_question(question)
    
        
    async def check_guess(self, guess: str) -> bool:
        """Use LLM to intelligently check if a guess matches the current object."""
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
            logger.info(f"Received game invitation for {target_audience} - choosing child-friendly object...")
            logger.debug(f"{language_rule}")
            await self.choose_new_object()
            await self.send_game_ready()
            
        elif msg_type == 'question_for_thinker':
            question = data.get('question', '')
            guesser = data.get('guesser', '')
            
            logger.info(f"Question from {guesser}: '{question}'")
            answer = await self.answer_question(question)
            logger.info(f"My answer: '{answer}'")
            
            await self.send_message('answer', {
                'question': question,
                'answer': answer,
                'guesser': guesser
            })
            
        elif msg_type == 'guess_for_thinker':
            guess = data.get('guess', '')
            guesser = data.get('guesser', '')
            
            logger.info(f"Guess from {guesser}: '{guess}'")
            correct = await self.check_guess(guess)
            
            if correct:
                logger.info(f"Correct! The object was '{self.current_object['name']}'")
            else:
                logger.info(f"Wrong! It's not '{guess}', it's '{self.current_object['name']}'")
            
            # Don't include actual_object to prevent leaking the secret on the public channel
            result_data = {
                'guesser': guesser,
                'guess': guess,
                'correct': correct
            }
            
            await self.send_message('guess_result', result_data)
            
        elif msg_type == 'game_over':
            winner = data.get('winner')
            if winner:
                logger.info(f"Game over! {winner} won by guessing '{self.current_object['name']}'!")
            else:
                logger.info(f"Game over! No one guessed '{self.current_object['name']}'.")
            
            self.running = False
            logger.info("Thinker agent exiting after game completion.")
            
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
        logger.info("Thinker ready with object - game can begin!")
        
    async def run(self):
        """Main agent loop - listens on public game session."""
        logger.info(f"Thinker Agent '{self.agent_name}' is connected and waiting for game start...")
        
        await self.send_ready()
        
        try:
            while self.running:
                try:
                    ctx, payload = await asyncio.wait_for(self.session.get_message(), timeout=1.0)
                    message = json.loads(payload.decode())
                    await self.handle_message(message)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error in public session: {e}")
                        await asyncio.sleep(1)
                    else:
                        break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        
        logger.info(f"Thinker '{self.agent_name}' has exited cleanly.")


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
        logger.info(f"Thinker Agent '{agent_name}' stopped by user.")
