"""
Translator observer agent that listens to all game messages and translates them to a target language.
"""

import asyncio
import json
import datetime
from typing import Optional
import slim_bindings
from .llm_agent import LLMAgent


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
        provider = slim_bindings.PyIdentityProvider.SharedSecret(
            identity=f"translator-{self.agent_name}",
            shared_secret=shared_secret
        )
        verifier = slim_bindings.PyIdentityVerifier.SharedSecret(
            identity=f"translator-{self.agent_name}",
            shared_secret=shared_secret
        )
        
        # Create local identity
        local_name = slim_bindings.PyName("school", "classroom", f"translator-{self.agent_name}")
        self.slim_app = await slim_bindings.Slim.new(local_name, provider, verifier)
        
        # Connect to SLIM service
        print(f"Connecting to SLIM at {slim_config.get('endpoint')}...")
        await self.slim_app.connect(slim_config)
        print(f"Translator Agent '{self.agent_name}' connected! ID: {self.slim_app.id_str}")
        print(f"Target Language: {self.target_language}")
        print(f"Full identity: {local_name}")
        
        # Wait for game session invitation
        print("Calling listen_for_session()... This will block until invitation received.")
        self.session = await self.slim_app.listen_for_session()
        print(f"Session invitation received! Joined game session!")
        print(f"Session ID: {self.session}")
        print(f"Now observing and translating messages to {self.target_language}...")
        
        # Establish secret session with Alice for monitoring
        await self.establish_secret_session_with_alice()
    
    async def establish_secret_session_with_alice(self):
        """Establish a 1:1 session with Alice to receive the secret object for monitoring."""
        try:
            print(f"Establishing secure 1:1 session with Alice for secret monitoring...")
            
            # Create a 1:1 session by creating a Group session with a unique channel
            secret_channel = slim_bindings.PyName("school", "classroom", f"secret-alice-{self.agent_name}")
            
            self.secret_session = await self.slim_app.create_session(
                slim_bindings.PySessionConfiguration.Group(
                    channel_name=secret_channel,
                    max_retries=5,
                    timeout=datetime.timedelta(seconds=10),
                    mls_enabled=True  # End-to-end encryption
                )
            )
            
            # Invite Alice to this secret channel
            alice_name = slim_bindings.PyName("school", "classroom", "thinker-Alice")
            await self.slim_app.set_route(alice_name)
            await self.secret_session.invite(alice_name)
            
            print(f"Secure 1:1 session established and Alice invited")
        except Exception as e:
            print(f"Failed to establish secret session: {e}")
            import traceback
            traceback.print_exc()
    
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
            print(f"Translation error: {e}")
            return f"[Translation error: {english_text}]"
    
    def extract_text_from_message(self, message: dict) -> Optional[str]:
        """Extract any text content from a message for translation."""
        # Convert the entire message to a readable string
        msg_type = message.get('type', '')
        data = message.get('data', {})
        
        # Build a simple text representation of the message
        text_parts = []
        
        # Add message type if available
        if msg_type:
            text_parts.append(f"[{msg_type}]")
        
        # Extract all string values from data
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
        
        # Only translate important game events, skip internal/duplicate messages
        important_messages = {
            'answer_from_thinker',  # Question and answer pair
            'guess_result',          # Guess and result
            'game_over',             # Game end summary
            'game_start'             # New game starting
        }
        
        if msg_type not in important_messages:
            return  # Skip internal/duplicate messages
        
        # Extract any text from the message
        english_text = self.extract_text_from_message(message)
        
        if english_text:
            # Translate to target language
            translated_text = await self.translate_text(english_text)
            
            # Output the translation
            print(f"[{self.target_language}] {translated_text}")
        
        # Exit after game over
        if msg_type == 'game_over':
            self.running = False
            print("Translator agent exiting after game completion.")
    
    async def run(self):
        """Main loop - listen for messages on both public and secret sessions."""
        async def listen_public_session():
            """Listen for messages on the public game session."""
            try:
                while self.running:
                    # Receive any message from the game session with timeout
                    try:
                        ctx, payload = await asyncio.wait_for(self.session.get_message(), timeout=1.0)
                        
                        if payload:
                            try:
                                message = json.loads(payload.decode())
                                await self.handle_message(message)
                            except json.JSONDecodeError:
                                continue
                    except asyncio.TimeoutError:
                        # Timeout is normal - just continue to check running flag
                        continue
                    
            except asyncio.CancelledError:
                print(f"Translator Agent '{self.agent_name}' is shutting down...")
            except Exception as e:
                if self.running:
                    print(f"Translator error: {e}")
        
        async def listen_secret_session():
            """Listen for secret messages from Alice."""
            # Wait for secret session to be established
            while self.running and not self.secret_session:
                await asyncio.sleep(0.1)
            
            if not self.secret_session:
                return
            
            try:
                while self.running:
                    try:
                        ctx, payload = await asyncio.wait_for(self.secret_session.get_message(), timeout=1.0)
                        message = json.loads(payload.decode())
                        msg_type = message.get('type')
                        
                        if msg_type == 'secret_object':
                            # Alice is sharing the secret with us for monitoring!
                            self.secret_object = message.get('data', {}).get('object')
                            print(f"[OBSERVER SECRET] Received secret from Alice: '{self.secret_object}'")
                            print(f"[OBSERVER SECRET] This was transmitted via secure 1:1 session - only Travis knows!")
                    except asyncio.TimeoutError:
                        # Timeout is normal - just continue to check running flag
                        continue
                    
            except asyncio.CancelledError:
                pass
            except Exception as e:
                if self.running:
                    print(f"Error in secret session: {e}")
        
        # Run both session listeners concurrently
        try:
            await asyncio.gather(
                listen_public_session(),
                listen_secret_session()
            )
        except Exception as e:
            print(f"Error in main loop: {e}")
        finally:
            print(f"Translator '{self.agent_name}' has exited cleanly.")
    
    async def start(self, slim_config: dict, shared_secret: str):
        """Start the translator agent."""
        await self.connect_to_slim(slim_config, shared_secret)
        await self.run()


def translator_main(slim_config_json: str, shared_secret: str, game_channel: str, agent_name: str, target_language: str):
    """Main entry point for the translator agent."""
    
    print(f"Starting Translator Agent '{agent_name}' for {target_language}...")
    
    async def run_translator():
        print(f"Initializing translator agent...")
        try:
            agent = TranslatorAgent(agent_name, target_language)
            print(f"Translator agent initialized for {target_language}")
            
            # Parse SLIM config
            slim_config = json.loads(slim_config_json)
            print(f"Parsed SLIM config")
            
            await agent.connect_to_slim(slim_config, shared_secret)
            print(f"Connected to SLIM")
            
            await agent.run()
        except Exception as e:
            print(f"Fatal error in translator: {e}")
            import traceback
            traceback.print_exc()
            raise
        
    try:
        asyncio.run(run_translator())
    except KeyboardInterrupt:
        print(f"Translator Agent '{agent_name}' stopped by user.")
    except Exception as e:
        print(f"Translator agent failed: {e}")

