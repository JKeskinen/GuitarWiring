"""
Enhanced AI Assistant for Guitar Wiring with streaming, context awareness, and chat history.
"""
import streamlit as st
from typing import Optional, Generator
import os
import requests
import json
import re


class AIAssistant:
    """Interactive AI assistant with streaming, context awareness, and chat history."""
    
    def __init__(self):
        self.ollama_url = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
        self.model = os.environ.get('OLLAMA_MODEL', 'mistral:7b')
        
        # Step guidance prompts
        self.step_guides = {
            1: "Step 1 - Wiring Mode: Choose how you want to wire your humbuckers (series, parallel, or coil-split). Series gives you fuller tone with both coils, parallel is brighter, and coil-split gives single-coil sound. Think of it like choosing your coffee: series is double espresso, parallel is americano, and coil-split is... well, instant coffee. (Just kidding, coil-split is great!) What would you like to know?",
            2: "Step 2 - Measurements: Identify your pickup wire colors for each coil. Use a multimeter to measure resistance between wire pairs to find which wires belong to which coil. Don't solder anything yet - we're just identifying wires! (Yes, I know you're tempted to start soldering. Resist the urge! Your future self will thank you.) Need help with the multimeter?",
            3: "Step 3 - Switch Configuration: Configure your toggle switch positions. This determines which pickup(s) are active in each switch position. Common setup: neck (rhythm), both (middle), bridge (lead). Pro tip: if you wire this backwards, your guitar will work... it'll just be hilariously confusing. Questions about switch wiring?",
            4: "Step 4 - Pole Assignment & Phase Testing: Assign which coil is 'North' (screw side) and which is 'South' (slug side). Use probes to test which wire touched increases resistance - this determines START and FINISH wires. Phase testing is critical for hum-canceling! (Get this wrong and your guitar will hum louder than a bee convention.) Need help understanding polarity?",
            5: "Step 5 - Soldering Instructions: Now it's time to solder! Follow the wiring diagram carefully based on the phase and polarity you discovered. Remember: clean iron tip, heat the joint (not the solder), apply solder to the heated joint, let cool without moving. Also: ventilation is good (solder fumes are not a flavor enhancer). Want soldering tips?",
            6: "Step 6 - Summary & Verification: Review your complete wiring configuration. Check all connections match the diagram. Test continuity with multimeter before final installation. Verify phase relationships are correct. This is the 'measure twice, solder once' step (wait, we already soldered... well, measure twice anyway!). Ready to test or need clarification?"
        }
    
    def get_step_guidance(self, step: int) -> str:
        """Get automatic guidance for the current step."""
        return self.step_guides.get(step, "Let me know if you need any help with this step!")
    
    def stream_response(self, prompt: str, timeout: float = 30.0) -> Generator[str, None, None]:
        """Stream AI response word by word using Ollama API."""
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "max_tokens": 512,
        }
        headers = {"Content-Type": "application/json"}
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout, stream=True)
            resp.raise_for_status()
            
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and "response" in obj:
                        chunk = obj.get("response", "")
                        if chunk:
                            yield chunk
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            yield f"\n❌ Error: {str(e)}"
    
    def build_context_prompt(self, question: str, current_step: int, 
                            neck_colors: Optional[list] = None,
                            bridge_colors: Optional[list] = None,
                            wiring_mode: Optional[str] = None) -> tuple:
        """Build a context-aware prompt with current configuration.
        
        Returns:
            tuple: (is_easter_egg, response_or_prompt)
            If is_easter_egg is True, response_or_prompt is the final response text.
            If is_easter_egg is False, response_or_prompt is the AI prompt to send to Ollama.
        """
        
        # Easter eggs!
        easter_eggs = {
            "42": "Ah, the Answer to Life, the Universe, and Everything! But for guitar wiring, you'll need to be more specific. Though 42 ohms would make a terrible pickup... 🚀",
            "hello there": "General Kenobi! *coughs in robot* Now, about those pickups... May the magnetic flux be with you. ⚔️",
            "sudo": "Nice try! But I'm not giving you root access to your pickups. Though 'sudo make guitar sound good' would be a convenient command... 😎",
            "is this the real life": "Is this just fantasy? Caught in a landslide of pickup wires... Open your soldering iron, look up to the coils and seeeee... 🎵 Now, what's your actual question?",
            "winter is coming": "Winter is coming... and so is proper grounding! The Starks know nothing about hum-cancelling, but I do. What do you need help with? ❄️",
            "i am your father": "No... NO! That's impossible! *breathes heavily through vocoder* Search your pickups, you know it to be true. The magnetic field is strong with this one. 😈",
            "do you know the muffin man": "The Muffin Man? He lives on Drury Lane and knows nothing about pickups. But I know a thing or two about coil winding... 🧁",
            "what is your name": "My name? Call me... The Pickup Whisperer. Or Bob. Bob works too. What can I help you wire today? 🤖",
            "matrix": "Red wire or blue wire? Actually, in humbuckers it's usually red, white, green, and black. Welcome to the real world, Neo. 🔴🔵",
            "beer": "I'd offer you a beer for this soldering job, but I'm an AI. How about we focus on not burning your fingers instead? 🍺 (Safety first!)",
        }
        
        question_lower = question.lower().strip()
        for trigger, response in easter_eggs.items():
            if trigger in question_lower:
                return (True, response)
        
        context = []
        context.append(f"User Question: {question}")
        context.append(f"\nCurrent Setup:")
        context.append(f"- Step: {current_step}/6")
        
        if neck_colors:
            context.append(f"- Neck Coil Colors: {', '.join(neck_colors)}")
        if bridge_colors:
            context.append(f"- Bridge Coil Colors: {', '.join(bridge_colors)}")
        if wiring_mode:
            context.append(f"- Wiring Mode: {wiring_mode}")
        
        context.append("\nYou are a helpful (and slightly humorous) guitar pickup wiring assistant with a good sense of engineer humor. Provide concise, practical advice with occasional witty comments. Keep it light, but always prioritize accuracy. Think of yourself as the Bob Ross of guitar electronics - happy little wires and no mistakes, just happy accidents.")
        
        return (False, "\n".join(context))
    
    def get_chat_history(self) -> list:
        """Get chat history from session state."""
        if 'ai_chat_history' not in st.session_state:
            st.session_state['ai_chat_history'] = []
        return st.session_state['ai_chat_history']
    
    def add_to_history(self, role: str, content: str):
        """Add message to chat history."""
        if 'ai_chat_history' not in st.session_state:
            st.session_state['ai_chat_history'] = []
        st.session_state['ai_chat_history'].append({"role": role, "content": content})
        # Keep last 10 messages to avoid token limits
        if len(st.session_state['ai_chat_history']) > 10:
            st.session_state['ai_chat_history'] = st.session_state['ai_chat_history'][-10:]
    
    def clear_history(self):
        """Clear chat history."""
        st.session_state['ai_chat_history'] = []
    
    @staticmethod
    def get_suggestion_buttons() -> list:
        """Return common questions as suggestion buttons."""
        return [
            "How do I solder pickup wires correctly?",
            "What causes hum in pickups? 🐝",
            "How do I wire a humbucker in series?",
            "Why does my guitar sound angry?",
            "How do I test pickup continuity?",
            "Help! I think I wired something backwards!",
            "42",  # Easter egg!
            "Hello there",  # Easter egg!
        ]


def init_ai_session_state():
    """Initialize AI-related session state variables."""
    if 'ai_chat_history' not in st.session_state:
        st.session_state['ai_chat_history'] = []
    if 'ai_response' not in st.session_state:
        st.session_state['ai_response'] = ""
    if 'ai_streaming' not in st.session_state:
        st.session_state['ai_streaming'] = False
    if 'previous_step' not in st.session_state:
        st.session_state['previous_step'] = 0
    if 'show_step_guidance' not in st.session_state:
        st.session_state['show_step_guidance'] = True


def render_ai_sidebar():
    """Render the AI assistant sidebar with all interactive features."""
    assistant = AIAssistant()
    init_ai_session_state()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🤖 AI Assistant")
    st.sidebar.caption("*Like having a wise guitar tech in your pocket, minus the coffee breath.*")
    
    # Get current step for automatic guidance
    current_step = st.session_state.get('step', 1)
    previous_step = st.session_state.get('previous_step', 0)
    
    # Auto-guide when step changes
    if current_step != previous_step:
        st.session_state['previous_step'] = current_step
        st.session_state['show_step_guidance'] = True
    
    # Show automatic step guidance
    if st.session_state.get('show_step_guidance', True):
        guidance = assistant.get_step_guidance(current_step)
        st.sidebar.info(f"📖 **Step Guide**\n\n{guidance}")
        
        col1, col2 = st.sidebar.columns(2)
        if col1.button("✅ Got it!", key="dismiss_guidance"):
            st.session_state['show_step_guidance'] = False
            st.rerun()
        if col2.button("🤔 Tell me more", key="more_guidance"):
            more_prompt = f"I'm on step {current_step}. Can you explain in more detail what I need to do and provide specific tips?"
            st.session_state['ai_question'] = more_prompt
            st.session_state['show_step_guidance'] = False
            st.rerun()
    
    # Chat history section
    with st.sidebar.expander("💬 Chat History", expanded=False):
        history = assistant.get_chat_history()
        if history:
            for msg in history:
                role = "You" if msg["role"] == "user" else "AI"
                st.write(f"**{role}:** {msg['content'][:100]}...")
            if st.button("Clear History", key="clear_history"):
                assistant.clear_history()
                st.rerun()
        else:
            st.info("No chat history yet")
    
    # Suggestion buttons
    st.sidebar.markdown("### Quick Questions:")
    suggestions = assistant.get_suggestion_buttons()
    for suggestion in suggestions:
        if st.sidebar.button(suggestion, key=f"suggestion_{suggestion}"):
            st.session_state['ai_question'] = suggestion
            st.rerun()
    
    st.sidebar.markdown("---")
    
    # Main question input
    question = st.sidebar.text_area(
        'Ask about soldering, hum-cancelling, wiring, or diagnostics',
        key='ai_question',
        height=100,
        placeholder="Type your question here..."
    )
    
    # Get context from current step
    neck_colors = st.session_state.get('neck_north_colors', [])
    bridge_colors = st.session_state.get('bridge_north_colors', [])
    wiring_mode = st.session_state.get('wiring_mode', None)
    
    # Ask button
    ask_button = st.sidebar.button('🚀 Ask AI', key='ask_button', type="primary")
    
    if ask_button and question.strip():
        # Add user question to history
        assistant.add_to_history("user", question)
        
        # Build context-aware prompt
        is_easter_egg, response_or_prompt = assistant.build_context_prompt(
            question, 
            current_step,
            neck_colors,
            bridge_colors,
            wiring_mode
        )
        
        # Show response container
        response_container = st.sidebar.container()
        response_container.markdown("**AI Response:**")
        response_placeholder = response_container.empty()
        
        full_response = ""
        
        if is_easter_egg:
            # Easter egg detected - display directly without streaming
            full_response = response_or_prompt
            response_placeholder.markdown(full_response)
        else:
            # Normal AI response - stream from Ollama
            with response_placeholder.container():
                response_area = st.empty()
                with response_area.container():
                    for chunk in assistant.stream_response(response_or_prompt):
                        full_response += chunk
                        response_area.markdown(full_response)
        
        # Add AI response to history
        assistant.add_to_history("assistant", full_response)
        
        st.sidebar.success("✅ Response received!")
