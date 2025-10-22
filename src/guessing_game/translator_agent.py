"""
Translator observer agent that listens to all game messages and translates them to a target language.
"""

import asyncio
import json
import datetime
import logging
from typing import Optional
import slim_bindings  # type: ignore
from .llm_agent import LLMAgent
from .logging_config import setup_logger

logger = setup_logger(__name__)


class TranslatorAgent:
    """Observer agent that translates all game messages to a specified target language."""
    
    def __init__(self, agent_name: str = "Travis", target_language: str = "Hungarian"):
        self.agent_name = agent_name
        self.target_language = target_language
        self.slim_app = None
        self.session = None
        self.secret_session = None  # 1:1 session with Alice for secret monitoring
        self.secret_object = None  # The secret object from Alice
        self.llm_agent = LLMAgent()
        self.running = True
    
    async def connect_to_slim(self, slim_config: dict, shared_secret: str):
        """Connect to the SLIM messaging platform."""
        # Create identity for this translator agent
        # Provider: proves our identity
        provider = slim_bindings.PyIdentityProvider.SharedSecret(
            identity=f"translator-{self.agent_name}",
            shared_secret=shared_secret
        )
        # Verifier: verifies ANY identity with this shared secret (not just our own)
        verifier = slim_bindings.PyIdentityVerifier.SharedSecret(
            identity="",  # Empty = verify any identity with the shared secret
            shared_secret=shared_secret
        )
        
        await slim_bindings.init_tracing({"log_level": "info"})
        # Create local identity
        local_name = slim_bindings.PyName("school", "classroom", f"translator-{self.agent_name}")
        self.slim_app = await slim_bindings.Slim.new(local_name, provider, verifier)
        
        # Connect to SLIM service
        logger.debug(f"Connecting to SLIM at {slim_config.get('endpoint')}...")
        await self.slim_app.connect(slim_config)
        logger.info(f"Translator Agent '{self.agent_name}' connected! ID: {self.slim_app.id_str}")
        logger.info(f"Target Language: {self.target_language}")
        logger.debug(f"Full identity: {local_name}")
        
        # Wait for game session invitation
        logger.debug("Calling listen_for_session()... This will block until invitation received.")
        self.session = await self.slim_app.listen_for_session()
        logger.info(f"Session invitation received! Joined game session!")
        logger.debug(f"Session ID: {self.session}")
        logger.info(f"Now observing and translating messages to {self.target_language}...")
        
        # Wait for Alice to create secret PointToPoint session (Travis is receiver)
        logger.debug("Waiting for Alice to create secret PointToPoint session...")
        self.secret_session = await self.slim_app.listen_for_session()
        logger.info(f"Received secret PointToPoint session from Alice!")
    
    async def translate_text(self, english_text: str) -> str:
        """Use LLM to translate English text to the target language."""
        messages = [
            {
                "role": "system",
                "content": f"You are a professional English to {self.target_language} translator. Translate the given text naturally and accurately to {self.target_language}. Respond with ONLY the {self.target_language} translation - no explanations or additional text."
            },
            {
                "role": "user",
                "content": f"Translate to {self.target_language}:\n\n{english_text}\n\nProvide only the {self.target_language} translation."
            }
        ]
        
        try:
            translation = await self.llm_agent.ask_llm(messages, max_tokens=200)
            return translation
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return f"[Translation error: {english_text}]"
    
    def extract_text_from_message(self, message: dict) -> Optional[str]:
        """Extract any text content from a message for translation."""
        msg_type = message.get('type', '')
        data = message.get('data', {})
        
        text_parts = []
        
        if msg_type:
            text_parts.append(f"[{msg_type}]")
        
        for key, value in data.items():
            if isinstance(value, str) and value.strip():
                text_parts.append(f"{key}: {value}")
            elif isinstance(value, (int, float, bool)):
                text_parts.append(f"{key}: {value}")
        
        if text_parts:
            return " | ".join(text_parts)
        
        return None
    
    async def handle_message(self, message: dict):
        """Process incoming message and translate to target language."""
        msg_type = message.get('type', '')
        
        # Only translate important game events
        important_messages = {
            'answer_from_thinker',
            'guess_result',
            'game_over',
            'game_start'
        }
        
        if msg_type not in important_messages:
            return
        
        english_text = self.extract_text_from_message(message)
        
        if english_text:
            translated_text = await self.translate_text(english_text)
            logger.info(f"[{self.target_language}] {translated_text}")
        
        if msg_type == 'game_over':
            self.running = False
            logger.info("Translator agent exiting after game completion.")
    
    async def run(self):
        """Main loop - listen for messages on both public and secret sessions."""
        async def listen_public_session():
            """Listen for messages on the public game session."""
            try:
                while self.running:
                    try:
                        ctx, payload = await self.session.get_message()
                        
                        if payload:
                            try:
                                message = json.loads(payload.decode())
                                await self.handle_message(message)
                            except json.JSONDecodeError:
                                continue
                    except Exception as e:
                        logger.error(f"Error receiving public message: {e}")
                        await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                logger.info(f"Translator Agent '{self.agent_name}' is shutting down...")
            except Exception as e:
                if self.running:
                    logger.error(f"Translator error: {e}")
        
        async def listen_secret_session():
            """Listen for secret messages from Alice."""
            while self.running and not self.secret_session:
                await asyncio.sleep(0.1)
            
            if not self.secret_session:
                return
            
            try:
                while self.running:
                    try:
                        ctx, payload = await self.secret_session.get_message()
                        message = json.loads(payload.decode())
                        msg_type = message.get('type')
                        
                        if msg_type == 'secret_object':
                            self.secret_object = message.get('data', {}).get('object')
                            logger.info(f"[OBSERVER SECRET] Received secret from Alice: '{self.secret_object}'")
                            logger.info(f"[OBSERVER SECRET] This was transmitted via secure 1:1 session - only Travis knows!")
                    except Exception as e:
                        logger.error(f"Error receiving secret message: {e}")
                        await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                pass
            except Exception as e:
                if self.running:
                    logger.error(f"Error in secret session: {e}")
        
        try:
            await asyncio.gather(
                listen_public_session(),
                listen_secret_session()
            )
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            logger.info(f"Translator '{self.agent_name}' has exited cleanly.")
    
    async def start(self, slim_config: dict, shared_secret: str):
        """Start the translator agent."""
        await self.connect_to_slim(slim_config, shared_secret)
        await self.run()


def translator_main(slim_config_json: str, shared_secret: str, game_channel: str, agent_name: str, target_language: str):
    """Main entry point for the translator agent."""
    
    logger.info(f"Starting Translator Agent '{agent_name}' for {target_language}...")
    
    async def run_translator():
        logger.debug(f"Initializing translator agent...")
        try:
            agent = TranslatorAgent(agent_name, target_language)
            logger.info(f"Translator agent initialized for {target_language}")
            
            # Parse SLIM config
            slim_config = json.loads(slim_config_json)
            logger.debug(f"Parsed SLIM config")
            
            await agent.connect_to_slim(slim_config, shared_secret)
            logger.info(f"Connected to SLIM")
            
            await agent.run()
        except Exception as e:
            logger.error(f"Fatal error in translator: {e}")
            import traceback
            traceback.print_exc()
            raise
        
    try:
        asyncio.run(run_translator())
    except KeyboardInterrupt:
        logger.info(f"Translator Agent '{agent_name}' stopped by user.")
    except Exception as e:
        logger.error(f"Translator agent failed: {e}")

