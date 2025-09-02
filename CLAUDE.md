# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FIREgenerator is a Streamlit-based web application that provides investment guidance through an AI-powered chatbot. The application uses Google OAuth for authentication, Supabase for data storage, and implements a sophisticated LangGraph-based conversation system for collecting user investment profiles.

## Key Architecture Components

### Main Application Structure

- **Entry Point**: `my_app/app.py` - Main Streamlit application with authentication and navigation
- **UI Modules**: Role-based page access system with separate modules for User/Admin roles
  - `my_app/ui/admin/` - Admin-specific functionality
  - `my_app/ui/dashboard/` - User dashboard components
  - `my_app/ui/settings/` - Application settings management
  - `my_app/ui/chatbot/` - Core chatbot interface and logic
- **Authentication**: Google OAuth integration with Supabase backend
- **Database**: Supabase for user profiles and session management

### LangGraph Chatbot System Architecture

The core chatbot is built using LangGraph with a sophisticated node-based conversation flow:

- **Graph Builder**: `my_app/ui/chatbot/langgraph_core/graph_builder.py` - Central orchestrator using StateGraph
- **State Management**: `my_app/ui/chatbot/langgraph_core/state/state.py` - Pydantic models with custom merge functions for conversation state
- **Node System**: Modular conversation nodes in `my_app/ui/chatbot/langgraph_core/nodes/`
  - `conversation_node.py` - Greeting and conversation initiation
  - `questions_node.py` - Fixed and generated question handling
  - `response_node.py` - Final response generation
  - `analyzed_node.py` - Goal analysis and state processing
- **Prompt Management**: YAML-based prompt templates in `my_app/ui/chatbot/langgraph_core/prompts/`
  - Separation of concerns: greeting, system prompts, goal analysis, question generation
- **LLM Integration**: `my_app/ui/chatbot/langgraph_core/llm_agents.py` - Google Generative AI integration

### State Management Pattern

The chatbot uses a sophisticated state merging system:

- `InputState`, `OutputState`, and `OverallState` schemas
- Custom merge functions for user answers aggregation
- Memory checkpointing for conversation persistence

### Conversation Flow

1. **start_conversation** - User greeting based on profile status ("onboarding", "editing", "completed")
2. **get_fixed_questions** - Serve predefined investment questions  
3. **get_generate_questions** - Generate dynamic follow-up questions using LLM
4. **generate_analyzed_state** - Process and analyze user responses
5. **get_analyzed_state** - Final response generation with investment profile summary

## Development Commands

### Running the Application

```bash
streamlit run my_app/app.py
```

### Installing Dependencies

```bash
pip install -r requirements.txt
```

### Development Workflow

- Use `_tests/MyNotebooks/` for experimental development and testing
- Refer to `_tests/17-LangGraph/` for LangGraph patterns and examples
- Test individual components using the notebook files in `_tests/MyNotebooks/`

## Key Dependencies and Integration Points

- **streamlit**: Main web framework with session state management
- **langgraph**: Conversation workflow orchestration with checkpointing
- **langchain-core**: Message handling and runnable interfaces
- **langchain-google-genai**: Google AI integration for LLM capabilities
- **supabase**: Database operations and OAuth authentication
- **pydantic**: Data validation and state schema definition
- **google-genai**: Direct Google Generative AI API integration

## Environment Setup Requirements

- Streamlit secrets configuration for Supabase credentials
- Google OAuth provider setup in Supabase dashboard
- Proper redirect URLs configured for OAuth flow
- Google API credentials for generative AI access

## Testing and Development Infrastructure

The `_tests/` directory structure:

- **`17-LangGraph/`**: Comprehensive LangGraph examples and patterns
  - Core features, structures, and use cases
  - RAG implementations and multi-agent patterns
- **`MyNotebooks/`**: Development notebooks for testing components
- **`langchain/`**: Basic LangChain integration examples

## Critical Implementation Details

- All conversation interactions are multiple-choice based (no free-form text input)
- User profile status drives conversation flow and available actions
- Graph execution uses interruption mechanism for interactive question handling
- Streamlit session state bridges web interface with LangGraph state management
- Custom state merging functions handle complex user answer aggregation
- YAML-based prompt management allows for easy content updates without code changes

## Node Architecture Deep Dive

The LangGraph system implements a sophisticated 8-node conversation flow with conditional routing:

### Node Categories by Function

- **Initialization**: `initialize_conversation` - Profile status-driven greeting
- **Content Generation**: `prepare_fixed_question_set`, `generate_follow_up_questions` - Multi-stage question delivery
- **Analysis**: `analyze_user_goal`, `evaluation_analysis` - LLM-powered response processing  
- **State Management**: `update_profile_status`, `build_output_state_from_analysis` - Profile completion tracking
- **Routing Logic**: Conditional edges based on profile status and validation results

### Critical State Patterns

- **Custom Merge Functions**: `merge_user_answers` aggregates responses across conversation sessions
- **Type-Safe State**: Pydantic models with `Annotated` fields for validation and documentation
- **Memory Persistence**: `MemorySaver` checkpointing allows conversation resumption
- **Multi-Schema Design**: Separate `InputState`, `OutputState`, and `OverallState` for clean interfaces

## Authentication & Session Management

- **OAuth Flow**: Google OAuth with Supabase backend handling token exchange
- **Session Bridge**: Streamlit session state bridges web interface with LangGraph state
- **Role-Based Access**: Navigation dynamically adjusts based on user role (User/Admin)
- **Profile Loading**: User data populated from Supabase `profiles` table on successful authentication

## Development Environment Configuration

- **Secrets Management**: Streamlit secrets for Supabase credentials (`st.secrets["supabase"]`)
- **OAuth Setup**: Google OAuth provider configuration in Supabase dashboard
- **Redirect URLs**: Proper OAuth redirect configuration for local/production environments
- **API Integration**: Google Generative AI credentials for LLM functionality
