"""
LLM-powered agent base class for intelligent question answering and reasoning.
"""

import json
import os
from typing import Dict, List, Optional
import openai


class LLMAgent:
    """Base class for LLM-powered game agents supporting both local Ollama and remote Azure OpenAI."""
    
    def __init__(self, model: str = None):
        # Setup LLM connection using generic environment variables
        self._setup_llm(model)
    
    def _setup_llm(self, model: str = None):
        """Setup LLM connection using generic environment variables."""
        self.model = model or os.getenv("LLM_MODEL")
        llm_url = os.getenv("LLM_URL")
        llm_api_key = os.getenv("LLM_API_KEY")
        
        if not self.model or not llm_url or not llm_api_key:
            print("LLM configuration incomplete in environment!")
            print("Required: LLM_MODEL, LLM_URL, and LLM_API_KEY")
            raise ValueError("Missing required LLM environment variables")
            
        self.client = openai.AsyncOpenAI(
            base_url=llm_url,
            api_key=llm_api_key
        )
        
        print(f"Using LLM: {self.model}")
        print(f"Endpoint: {llm_url}")
    
    async def ask_llm(self, messages: List[Dict[str, str]], max_tokens: int = 150) -> str:
        """Send a request to the LLM and get a response."""
        try:
            # Use temperature=1.0 for all models to ensure compatibility
            temperature = 1.0
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            mode_desc = "LLM"
            print(f"{mode_desc} error: {e}")
            return "I'm having trouble thinking right now."
    


class LLMThinkerAgent(LLMAgent):
    """LLM-powered thinker agent that chooses objects and answers questions intelligently."""
    
    def __init__(self, model: str = None):
        super().__init__(model)
        self.current_object = None
        self.object_context = None
    
    async def choose_object(self) -> str:
        """Use LLM to choose an interesting object for the guessing game."""
        import random
        
        # Rotate through different English example sets to encourage variety
        example_sets = [
            ["apple", "car", "book", "cat"],
            ["ball", "tree", "spoon", "dog"], 
            ["shoe", "bicycle", "door", "fish"],
            ["cup", "bird", "chair", "cake"],
            ["hat", "bus", "lamp", "bear"]
        ]
        
        # Add variety with different focus areas each time
        focus_areas = [
            "Think about objects from around the house, school, or outside",
            "Consider things children play with, eat, or use daily", 
            "Focus on animals, plants, or natural objects kids see often",
            "Think of vehicles, furniture, or things that move",
            "Consider food, toys, or colorful objects children love"
        ]
        
        # Random selections for variety
        examples = random.choice(example_sets)
        focus = random.choice(focus_areas)
        categories = random.sample([
            "fruits", "vegetables", "animals", "toys", "school supplies", 
            "sports equipment", "household items", "vehicles", "foods", 
            "clothing", "nature objects", "furniture", "tools"
        ], 6)  # Pick 6 random categories
        
        examples_text = ", ".join([f"'{ex}'" for ex in examples])
        categories_text = ", ".join(categories)
        
        # Add timestamp randomness to prevent LLM pattern repetition
        import time
        time_seed = int(time.time()) % 1000
        
        messages = [
            {
                "role": "system",
                "content": "You are playing a guessing game with children. Choose objects that kids would definitely know and recognize from their daily life. You MUST respond with exactly ONE ENGLISH WORD only. BE CREATIVE AND VARIED - avoid repeating previous choices!"
            },
            {
                "role": "user", 
                "content": f"Game #{time_seed}: Choose ONE object for a guessing game with children. {focus}. Consider: {categories_text}. The key is that every child would recognize it. Be varied and interesting! Respond with ONLY a SINGLE ENGLISH WORD - no phrases, no compound words, just one simple English word like {examples_text}. The game will be played in English."
            }
        ]
        
        self.current_object = await self.ask_llm(messages, max_tokens=20)
        
        # Get detailed context about the object for answering questions
        await self._get_object_context()
        
        return self.current_object
    
    async def _get_object_context(self):
        """Get detailed information about the chosen object for question answering."""
        messages = [
            {
                "role": "system",
                "content": "You are an expert on objects and their properties. Provide comprehensive information about the given object to help answer yes/no questions accurately."
            },
            {
                "role": "user",
                "content": f"Describe the key properties of a '{self.current_object}' that would be relevant for a guessing game. Include: size, color, material, living/non-living, location typically found, function, sounds it makes, etc. Keep it factual and child-appropriate."
            }
        ]
        
        self.object_context = await self.ask_llm(messages, max_tokens=300)
    
    async def answer_question(self, question: str) -> str:
        """Use LLM to intelligently answer yes/no questions about the object."""
        messages = [
            {
                "role": "system",
                "content": f"You are playing a guessing game with children in English. You have chosen the object '{self.current_object}' - something every child would know. Answer questions accurately from a child's perspective. You MUST respond with ONLY 'yes' or 'no' in English - NO OTHER WORDS.\n\nObject context: {self.object_context}"
            },
            {
                "role": "user",
                "content": f"Question about '{self.current_object}': {question}\n\nThink like an child would understand this object. Answer with ONLY 'yes' or 'no' in English."
            }
        ]
        
        return await self.ask_llm(messages, max_tokens=10)
    
    async def check_guess(self, guess: str) -> bool:
        """Check if a guess matches the current object."""
        if not self.current_object:
            return False
        
        # First, do a simple case-insensitive comparison
        if guess.lower().strip() == self.current_object.lower().strip():
            return True
            
        # If exact match fails, use LLM for flexible matching (handles synonyms, plural forms, etc.)
        messages = [
            {
                "role": "system", 
                "content": f"You are checking if a guess matches the secret object '{self.current_object}'. Consider synonyms, plural/singular forms, and reasonable variations. Be generous with matches."
            },
            {
                "role": "user",
                "content": f"Does the guess '{guess}' match semantically the object '{self.current_object}'? Answer only 'yes' or 'no'."
            }
        ]
        
        result = await self.ask_llm(messages, max_tokens=5)
        return result.lower().startswith("yes")


class LLMGuesserAgent(LLMAgent):
    """LLM-powered guesser agent with different personality strategies."""
    
    def __init__(self, agent_name: str, strategy: str, model: str = None):
        super().__init__(model)
        self.agent_name = agent_name
        self.strategy = strategy
        self.game_history = []
        self.my_guesses = 0  # Track my own guesses
    
    def update_game_history(self, game_log: List[Dict]):
        """Update the agent's memory of the game so far."""
        self.game_history = game_log
        
        # Count my own guesses from the game log
        self.my_guesses = len([entry for entry in game_log 
                              if entry.get('type') == 'guess' and 
                              self.agent_name in entry.get('guesser', '')])
    
    async def should_make_guess(self) -> bool:
        """Use LLM to decide whether to ask another question or make a guess."""
        if not self.game_history:
            return False
        
        # Get recent Q&A for context
        recent_qa = []
        for entry in self.game_history[-10:]:  # Last 10 entries
            if entry['type'] == 'question':
                recent_qa.append(f"Q: {entry['question']} A: {entry['answer']}")
        
        qa_text = "\n".join(recent_qa) if recent_qa else "No questions asked yet."
        questions_asked = len([e for e in self.game_history if e['type'] == 'question'])
        guesses_made = len([e for e in self.game_history if e['type'] == 'guess'])
        
        messages = [
            {
                "role": "system",
                "content": f"You are {self.agent_name}, a {self.strategy} guesser in a COMPETITIVE guessing game. This is a RACE - your goal is to be the FIRST to correctly guess the mystery object and WIN before the other players do! You have exactly 3 guesses maximum. Use them wisely to beat your opponents!"
            },
            {
                "role": "user",
                "content": f"COMPETITIVE GAME STATUS:\n- Questions asked by all players: {questions_asked}/20\n- YOUR guesses used: {self.my_guesses}/3 (you get 3 total)\n- Recent Q&A:\n{qa_text}\n\nThis is a RACE! Should you make a guess now to try to WIN, or ask another question first? Remember: other players are also trying to guess. If you're confident, GUESS to win! If you need more info, ask a QUESTION. Answer only 'GUESS' or 'QUESTION'."
            }
        ]
        
        decision = await self.ask_llm(messages, max_tokens=10)
        return decision.upper().strip().startswith("GUESS")
    
    async def ask_question(self) -> str:
        """Use LLM to generate strategic questions based on personality."""
        
        # Get recent Q&A for context
        recent_qa = []
        for entry in self.game_history[-8:]:  # Last 8 entries
            if entry['type'] == 'question':
                recent_qa.append(f"Q: {entry['question']} A: {entry['answer']}")
        
        qa_text = "\n".join(recent_qa) if recent_qa else "No questions asked yet."
        
        strategy_prompts = {
            "systematic": "You ask logical, methodical questions to systematically narrow down possibilities. Start with broad categories (living/non-living, size, etc.) then get more specific. Be efficient - this is a competitive race!",
            "creative": "You ask imaginative, fun questions that think outside the box. You consider how objects make people feel, their cultural significance, and creative associations. Use creativity to get insights others might miss!",
            "random": "You ask varied questions from different angles, sometimes surprising others with unexpected approaches. You're spontaneous and unpredictable. Keep opponents guessing your strategy!"
        }
        
        strategy_guidance = strategy_prompts[self.strategy]
        
        messages = [
            {
                "role": "system",
                "content": f"You are in a COMPETITIVE guessing game race with other players! The mystery object is something every child would know from their daily life. You need to be the FIRST to guess correctly and WIN! You have exactly 3 guesses maximum - use them strategically.\n\nYour strategy: {strategy_guidance}"
            },
            {
                "role": "user",
                "content": f"GAME SITUATION:\n{qa_text}\n\nThis is a RACE - ask a strategic yes/no question IN ENGLISH to help you win! The object is something any child would know from daily life. Make your question count - other players are also trying to guess! Ask only the question in English. Questions should be properly formed English sentences that children would understand."
            }
        ]
        
        return await self.ask_llm(messages, max_tokens=30)
    
    async def make_guess(self) -> str:
        """Use LLM to make an educated guess based on gathered information."""
        
        # Compile all Q&A for analysis
        qa_pairs = []
        
        for entry in self.game_history:
            if entry['type'] == 'question':
                qa_pairs.append(f"Q: {entry['question']} A: {entry['answer']}")
        
        qa_text = "\n".join(qa_pairs) if qa_pairs else "No information available."
        
        # Get ALL wrong guesses from ALL players to avoid repeating them
        wrong_guesses = []
        other_player_guesses = []
        my_wrong_guesses = []
        
        for entry in self.game_history:
            if entry.get('type') == 'guess' and not entry.get('correct', False):
                guess = entry.get('guess', '')
                wrong_guesses.append(guess)
                
                # Track whether this was my guess or another player's guess
                if self.agent_name in entry.get('guesser', ''):
                    my_wrong_guesses.append(guess)
                else:
                    other_player_guesses.append(guess)
        
        wrong_guesses_text = ""
        if wrong_guesses:
            unique_wrong_guesses = list(set(wrong_guesses))  # Remove duplicates
            wrong_guesses_text = f"\n\nIMPORTANT - These guesses have already been tried by ALL players and are WRONG (DO NOT repeat ANY of these):\n" + ", ".join(unique_wrong_guesses)
            
            if other_player_guesses:
                unique_other_guesses = list(set(other_player_guesses))
                wrong_guesses_text += f"\n\nOther players already guessed wrong: {', '.join(unique_other_guesses)} - Learn from their mistakes!"
        
        strategy_guidance = {
            "systematic": "Analyze clues methodically and logically to deduce the most likely object.",
            "creative": "Think imaginatively and consider unique objects that fit the clues.",
            "random": "Consider various possibilities and make an intuitive guess."
        }[self.strategy]
        
        messages = [
            {
                "role": "system",
                "content": f"You are {self.agent_name} in a COMPETITIVE RACE to guess the mystery object FIRST and WIN! This is your chance to beat the other players. You have exactly 3 guesses total - this is guess #{self.my_guesses + 1}/3. The object is something every child would know. NEVER repeat a wrong guess!\n\nYour strategy: {strategy_guidance}"
            },
            {
                "role": "user",
                "content": f"FINAL GUESS TIME - This is your chance to WIN the race!\n\nAll the clues gathered by everyone:\n{qa_text}{wrong_guesses_text}\n\nWhat object fits ALL the clues and hasn't been guessed wrong yet? This could be your WINNING moment! Learn from other players' wrong guesses and think of anything a child would know from daily life. Make this guess count - respond with only the English word for the object. Beat the other players!"
            }
        ]
        
        return await self.ask_llm(messages, max_tokens=20)
