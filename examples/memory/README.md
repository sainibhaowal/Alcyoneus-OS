# Personalized Agent with Mem0 + Cloud Qdrant

This directory contains examples of personalized AI agents built with Alcyoneus OS, Mem0 and Cloud Qdrant for long-term memory storage.

## 🏗️ Architecture

```
Alcyoneus OS (Agent Framework)
    ↓
Mem0 (Memory Management)
    ↓
Cloud Qdrant (Vector Storage)
    ↓
Gemini (LLM + Embeddings)
```

## 📋 Prerequisites

### 1. Environment Setup

Create a `.env` file in your project root:

```env
# Google AI (for Gemini models and embeddings)
GOOGLE_API_KEY=your_google_api_key_here

# Mem0 Cloud Service
MEM0_API_KEY=your_mem0_api_key_here

# Qdrant Cloud (768 dimensions for Gemini embeddings)
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key_here
```

### 2. Required Dependencies

Install the required packages:

```bash
# Core dependencies
pip install alcyoneus mem0ai python-dotenv

# Optional: For local development/testing
pip install qdrant-client
```

### 3. Service Setup

#### Google AI Platform
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Create an API key
3. Add to `.env` as `GOOGLE_API_KEY`

#### Mem0 Cloud
1. Sign up at [Mem0](https://app.mem0.ai/)
2. Get your API key from the dashboard
3. Add to `.env` as `MEM0_API_KEY`

#### Qdrant Cloud
1. Sign up at [Qdrant Cloud](https://cloud.qdrant.io/)
2. Create a cluster
3. Get your cluster URL and API key
4. Add to `.env` as `QDRANT_URL` and `QDRANT_API_KEY`

## 🚀 Examples

### 1. Simple Personalized Agent (`simple_personalized_agent.py`)

A streamlined example showing basic memory integration:

```python
from simple_personalized_agent import SimplePersonalizedAgent
import asyncio

async def chat_example():
    agent = SimplePersonalizedAgent()

    # The agent remembers across conversations
    response1 = await agent.chat("Hi, I'm Alice and I love hiking!", "alice")
    response2 = await agent.chat("What outdoor activities do I enjoy?", "alice")

    print(response1)
    print(response2)

asyncio.run(chat_example())
```

**Run it:**
```bash
cd examples/memory
python simple_personalized_agent.py
```

### 2. Advanced Personalized Agent (`personalized_agent_qdrant.py`)

A comprehensive example with sophisticated memory management:

**Features:**
- Multi-node Alcyoneus OS graph
- Advanced memory retrieval and storage
- User preference extraction
- Session management
- Interactive chat mode

**Run demo conversation:**
```bash
cd examples/memory
python personalized_agent_qdrant.py demo
```

**Run interactive mode:**
```bash
cd examples/memory
python personalized_agent_qdrant.py
```

**Interactive commands:**
- Type normally to chat
- `memories` - View your stored memories
- `quit` - Exit the chat

## 🧠 How Memory Works

### Memory Storage
```python
# Automatic storage after each interaction
interaction = [
    {"role": "user", "content": "I love pizza"},
    {"role": "assistant", "content": "Great! What's your favorite topping?"}
]

memory.add(interaction, user_id="alice", metadata={"app_id": "my-agent"})
```

### Memory Retrieval
```python
# Semantic search for relevant memories
memories = memory.search(
    query="What food do I like?",
    user_id="alice",
    limit=5
)
```

### Memory Context Integration
The agent automatically:
1. Searches for relevant memories based on user input
2. Includes memory context in the system prompt
3. Generates personalized responses
4. Stores new interactions for future reference

## 📊 Vector Storage Configuration

The examples are optimized for **Gemini embeddings (768 dimensions)**:

```python
config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "url": os.getenv('QDRANT_URL'),
            "api_key": os.getenv('QDRANT_API_KEY'),
            "embedding_model_dims": 768,  # Gemini embedding size
            "collection_name": "your_collection_name"
        }
    },
    "embedder": {
        "provider": "gemini",
        "config": {
            "model": "models/text-embedding-004"  # Latest Gemini embedding
        }
    }
}
```

## 🔧 Customization

### Change LLM Model
```python
# In the config
"llm": {
    "provider": "gemini",
    "config": {
        "model": "gemini-2.0-flash-exp",  # or gemini-2.0-flash-thinking-exp
        "temperature": 0.7,
        "max_tokens": 1500
    }
}
```

### Adjust Memory Retrieval
```python
# Change number of memories retrieved
memories = memory.search(query, user_id=user_id, limit=10)  # Default: 5

# Add metadata filtering
memories = memory.search(
    query,
    user_id=user_id,
    filters={"app_id": "specific-app"}
)
```

### Customize Memory Storage
```python
# Add custom metadata
metadata = {
    "app_id": "my-agent",
    "session_id": "session_123",
    "conversation_type": "support",
    "timestamp": datetime.now().isoformat()
}

memory.add(interaction, user_id=user_id, metadata=metadata)
```

## 🐛 Troubleshooting

### Common Issues

1. **Missing API Keys**
   ```bash
   ❌ Missing required environment variables: GOOGLE_API_KEY
   ```
   Solution: Check your `.env` file has all required keys

2. **Qdrant Connection Error**
   ```bash
   ❌ Error retrieving memories: Connection failed
   ```
   Solution: Verify `QDRANT_URL` and `QDRANT_API_KEY` are correct

3. **Memory Storage Fails**
   ```bash
   ❌ Memory storage error: Invalid user_id
   ```
   Solution: Ensure `user_id` is a non-empty string

4. **Embedding Dimension Mismatch**
   ```bash
   ❌ Vector dimension mismatch: expected 768, got 1536
   ```
   Solution: Use `embedding_model_dims: 768` for Gemini embeddings

5. **Configuration Validation Error**
   ```bash
   ❌ Extra fields not allowed: vector_size, distance
   ```
   Solution: Use `embedding_model_dims` instead of `vector_size` in Mem0 config

### Debug Mode

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📚 Learn More

- [Alcyoneus OS Documentation](https://github.com/alcyoneus-os/alcyoneus)
- [Mem0 Documentation](https://docs.mem0.ai/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [OpenAI Python SDK](https://github.com/openai/openai-python)

## 💡 Next Steps

Try extending the examples:
1. Add multiple agent types with different memory contexts
2. Implement memory pruning/summarization
3. Add conversation threading
4. Create specialized memory categories (preferences, facts, history)
5. Integrate with external data sources
