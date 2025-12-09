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
                            wiring_mode: Optional[str] = None) -> str:
        """Build a context-aware prompt with current configuration."""
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
        
        context.append("\nYou are a helpful guitar pickup wiring assistant. Provide concise, practical advice.")
        
        return "\n".join(context)
    
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
            "What causes hum in pickups?",
            "How do I wire a humbucker in series?",
            "What's the difference between neck and bridge pickups?",
            "How do I test pickup continuity?",
            "What wire gauge should I use?",
        ]


def init_ai_session_state():
    """Initialize AI-related session state variables."""
    if 'ai_chat_history' not in st.session_state:
        st.session_state['ai_chat_history'] = []
    if 'ai_response' not in st.session_state:
        st.session_state['ai_response'] = ""
    if 'ai_streaming' not in st.session_state:
        st.session_state['ai_streaming'] = False


def render_ai_sidebar():
    """Render the AI assistant sidebar with all interactive features."""
    assistant = AIAssistant()
    init_ai_session_state()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🤖 AI Assistant")
    
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
    current_step = st.session_state.get('step', 1)
    neck_colors = st.session_state.get('neck_north_colors', [])
    bridge_colors = st.session_state.get('bridge_north_colors', [])
    wiring_mode = st.session_state.get('wiring_mode', None)
    
    # Ask button
    ask_button = st.sidebar.button('🚀 Ask AI', key='ask_button', type="primary")
    
    if ask_button and question.strip():
        # Add user question to history
        assistant.add_to_history("user", question)
        
        # Build context-aware prompt
        context_prompt = assistant.build_context_prompt(
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
        
        # Stream response
        with response_placeholder.container():
            response_area = st.empty()
            with response_area.container():
                for chunk in assistant.stream_response(context_prompt):
                    full_response += chunk
                    response_area.markdown(full_response)
        
        # Add AI response to history
        assistant.add_to_history("assistant", full_response)
        
        st.sidebar.success("✅ Response received!")
