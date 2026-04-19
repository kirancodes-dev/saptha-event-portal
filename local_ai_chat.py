import ollama

# Start a conversation history
messages = []

print("Local AI Chat Started. Type 'quit' to exit.\n")

while True:
    user_input = input("You: ")
    
    if user_input.lower() == 'quit':
        break
        
    # Add the user's message to the history
    messages.append({'role': 'user', 'content': user_input})
    
    # Send the entire conversation history to the model
    response = ollama.chat(model='llama3.2:1b', messages=messages)
    ai_response = response['message']['content']
    
    # Print the AI's response and add it to the history
    print(f"\nAI: {ai_response}\n")
    messages.append({'role': 'assistant', 'content': ai_response})
