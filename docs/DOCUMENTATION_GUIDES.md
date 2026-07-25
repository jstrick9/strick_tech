# Agentic OS — Documentation Slide Decks & Screenshot Guides

## Quick-Start Guide Collection

---

# GUIDE 1: Chat with AI in 60 Seconds

## Slide Deck

### Slide 1 — Title
**Chat with AI in 60 Seconds**
*Agentic OS Quick-Start Guide*
- Your first conversation is just 4 steps away
- Works with 140+ AI models

### Slide 2 — Step 1: Open Chat
**Click "Chat" in the left sidebar**
- It's the first item in "Getting Started"
- Or press `⌘/` from anywhere
- The chat pane opens with a welcome screen

### Slide 3 — Step 2: Connect AI
**Choose your AI backend**
- **Option A**: Install Ollama (free, local) — detected automatically
- **Option B**: Paste an OpenRouter API key (free tier available) — go to Settings → Connect AI
- **Option C**: One-click setup modal appears on first visit

### Slide 4 — Step 3: Pick a Model
**Select from 140+ models**
- Click the model dropdown in the chat header
- Cloud models: Claude, GPT-4o, Gemini, Llama, Qwen
- Local models: Any Ollama model
- Start with "Llama 3.3 70B" (free) or "Claude 3.5 Sonnet" (best quality)

### Slide 5 — Step 4: Start Chatting
**Type anything and press Enter**
- Your AI responds in real-time with streaming
- Use the ⏹ button to stop generation
- Messages are saved automatically
- Try: "Explain what FastAPI is in simple terms"

### Slide 6 — Pro Tips
**Get more from Chat**
- `/help` — see all available commands
- `/swarm` — run multiple agents on the same question
- `/code` — ask AI to write code
- Attach files by dragging them into the chat
- Use the 🧠 Memory button to ground responses in your knowledge base

---

## Screenshot Guide

### Screenshot 1: Application Launch
**What to capture**: The full application window after first launch
**Description**: Shows the left sidebar with "Getting Started" expanded (Chat, Code Studio, Templates, Memory, Tasks, Settings), the empty chat pane with "How can I help you today?" message, and the topbar with the search bar.

### Screenshot 2: Quick Setup Modal
**What to capture**: The one-click setup modal that appears on first visit
**Description**: Shows the modal with auto-detection status for Ollama and OpenRouter, the API key input field, and the "Start Chatting" button.

### Screenshot 3: Model Selector
**What to capture**: The model dropdown expanded in the chat header
**Description**: Shows the dropdown with Cloud AI group (Claude, GPT-4o, Gemini, Llama, Qwen), Local (Ollama) group, and Custom group.

### Screenshot 4: First Chat Message
**What to capture**: A chat conversation with one user message and one AI response
**Description**: Shows the user message "Explain what FastAPI is" with the AI's streaming response, including the model badge, message actions, and the stop button visible.

### Screenshot 5: Chat with File Attachment
**What to capture**: The chat with a file attached and the attachment tray visible
**Description**: Shows the file chip in the attachment tray, the drag-and-drop overlay, and the file preview in the message.

---

# GUIDE 2: Create Your First AI Agent

## Slide Deck

### Slide 1 — Title
**Create Your First AI Agent**
*Give your AI a specialized role and personality*

### Slide 2 — Step 1: Open Agent Panel
**Click the agent selector in the chat header**
- Or go to Settings → AI Agents
- See the list of built-in agents (Brain, Orchestrator, Builder, Specs)

### Slide 3 — Step 2: Create an Agent
**Click "+ Add Agent"**
- Name: Give it a descriptive name (e.g., "Code Reviewer")
- Role: Describe what it does (e.g., "Expert code reviewer")
- System Prompt: Define its personality and instructions
- Model: Choose which AI model it uses
- Avatar: Pick an emoji

### Slide 4 — Step 3: Write a System Prompt
**Define your agent's expertise**
- Example: "You are an expert Python code reviewer. Focus on security, performance, and readability. Always provide specific line numbers and concrete suggestions."
- Be specific about what the agent should and shouldn't do
- Include any domain knowledge it needs

### Slide 5 — Step 4: Test and Refine
**Chat with your new agent**
- Select it from the dropdown in any chat
- Try different types of questions
- Adjust the system prompt based on results
- Different agents can use different models

---

## Screenshot Guide

### Screenshot 1: Agent Selector Dropdown
**What to capture**: The agent/persona dropdown expanded in the chat header
**Description**: Shows "Direct AI Chat" as default, with specialized agents listed below (Brain, Orchestrator, Builder, Specs).

### Screenshot 2: Agent Creation Modal
**What to capture**: The agent creation/editing modal
**Description**: Shows fields for name, role, system prompt, model selection, and avatar picker.

### Screenshot 3: Agent Chat
**What to capture**: A conversation with a custom agent
**Description**: Shows the agent's avatar and name in the message header, with a specialized response that demonstrates the agent's expertise.

---

# GUIDE 3: Build Your First Workflow

## Slide Deck

### Slide 1 — Title
**Build Your First Workflow**
*Chain multiple AI operations into automated pipelines*

### Slide 2 — Step 1: Open Workflow Builder
**Click "Workflows" in the sidebar**
- Under "Build & Deploy" group
- Or use the command palette (⌘K) and type "workflow"

### Slide 3 — Step 2: Add Nodes
**Drag nodes from the palette**
- Agent nodes: Send prompts to AI models
- Transform nodes: Process and filter data
- Decision nodes: Branch based on conditions
- Output nodes: Save or display results

### Slide 4 — Step 3: Connect Nodes
**Draw edges between nodes**
- Drag from output port to input port
- Data flows from top to bottom
- Multiple inputs can feed one node

### Slide 5 — Step 4: Configure and Run
**Set up each node's configuration**
- Agent nodes: Set prompt, model, temperature
- Click "Run" to execute the workflow
- Watch real-time execution in the DAG view

---

## Screenshot Guide

### Screenshot 1: Empty Workflow Canvas
**What to capture**: The workflow builder with an empty canvas
**Description**: Shows the node palette on the left, the empty canvas in the center, and the properties panel on the right.

### Screenshot 2: Workflow with Connected Nodes
**What to capture**: A simple 3-node workflow (Input → Agent → Output)
**Description**: Shows nodes connected with edges, with the agent node's configuration visible.

### Screenshot 3: Workflow Execution
**What to capture**: A running workflow with execution progress
**Description**: Shows nodes with green checkmarks (completed), a blue highlight (currently running), and the output appearing in real-time.

---

# GUIDE 4: Spec-Driven Development

## Slide Deck

### Slide 1 — Title
**Spec-Driven Development**
*Plan before you code — Requirements → Design → Tasks → Code*

### Slide 2 — Step 1: Open Spec Builder
**Click "Spec Builder" in the sidebar**
- Under "Build & Deploy" group
- Start with a plain English description of what you want to build

### Slide 3 — Step 2: Describe What You Want
**Write a clear feature description**
- Example: "Build a user authentication system with JWT tokens, password reset, and email verification"
- The more detail, the better the generated specs

### Slide 4 — Step 3: Review Generated Specs
**AI generates 4 documents**
- Requirements: User stories in EARS notation
- Architecture: System design and component diagram
- Tasks: Dependency-mapped task list
- Acceptance Criteria: Test conditions for each requirement

### Slide 5 — Step 4: Execute the Plan
**Run the pipeline**
- Tasks are executed in dependency order
- Independent tasks run in parallel
- Review generated code before applying changes

---

## Screenshot Guide

### Screenshot 1: Spec Builder Input
**What to capture**: The spec builder with a description being typed
**Description**: Shows the text input area with a sample description, the "Generate Specs" button, and the progress indicator.

### Screenshot 2: Generated Requirements
**What to capture**: The generated requirements document
**Description**: Shows user stories in EARS notation with acceptance criteria.

### Screenshot 3: Task Dependency Graph
**What to capture**: The task dependency visualization
**Description**: Shows tasks as nodes with dependency arrows, indicating execution order.

---

# GUIDE 5: Build a Document Q&A System (RAG)

## Slide Deck

### Slide 1 — Title
**Build a Document Q&A System**
*Ask questions about your documents — no hallucination*

### Slide 2 — Step 1: Open RAG Builder
**Click "Knowledge Search" in the sidebar**
- Under "Monitoring & Security" group
- Create a new pipeline

### Slide 3 — Step 2: Create a Pipeline
**Configure your knowledge base**
- Name: Give it a descriptive name
- Chunk size: 512 tokens (recommended)
- Embedding model: Nomic Embed Text (default)

### Slide 4 — Step 3: Add Documents
**Ingest your content**
- Paste text directly
- Upload files (PDF, Word, text, code)
- Connect to Obsidian vault
- Documents are chunked and indexed automatically

### Slide 5 — Step 4: Ask Questions
**Get cited answers**
- Type your question in the search box
- AI answers using only your documents
- Sources are cited with page numbers
- No hallucination — only what's in your docs

---

## Screenshot Guide

### Screenshot 1: RAG Pipeline List
**What to capture**: The RAG pipelines list view
**Description**: Shows existing pipelines with their names, document counts, and status.

### Screenshot 2: Document Upload
**What to capture**: The document upload interface
**Description**: Shows the drag-and-drop upload area, file list, and processing status.

### Screenshot 3: Q&A Results
**What to capture**: A question with a cited answer
**Description**: Shows the question, the AI's answer with highlighted citations, and the source documents listed below.

---

# GUIDE 6: Build an App with Code Studio

## Slide Deck

### Slide 1 — Title
**Build an App with Code Studio**
*Monaco editor + live preview + AI assistance*

### Slide 2 — Step 1: Open Studio
**Click "Code Studio" in the sidebar**
- Or press ⌘2
- Shows the file tree, Monaco editor, and live preview

### Slide 3 — Step 2: Start from a Template
**Choose a template or start blank**
- Open the Templates pane (📋 in sidebar)
- Pick a template (SaaS, Dashboard, Portfolio, etc.)
- One click to scaffold into your workspace

### Slide 4 — Step 3: Edit with AI
**Use the built-in AI assistant**
- Type changes in the editor
- Or ask AI to modify code in the chat panel
- AI shows a diff preview before applying changes

### Slide 5 — Step 4: Preview Live
**See changes instantly**
- Live preview updates as you type
- Toggle between desktop and mobile views
- Take screenshots for documentation

---

## Screenshot Guide

### Screenshot 1: Studio Layout
**What to capture**: The full Studio pane layout
**Description**: Shows the file tree on the left, Monaco editor in the center, and live preview on the right, with the split resizer visible.

### Screenshot 2: Template Gallery
**What to capture**: The template gallery with cards
**Description**: Shows template cards with icons, titles, descriptions, and "Deploy" buttons.

### Screenshot 3: AI Code Modification
**What to capture**: The AI chat panel in Studio showing a code change
**Description**: Shows the user asking "Add dark mode support" and the AI generating a diff preview.

---

# GUIDE 7: Multi-Agent Swarm

## Slide Deck

### Slide 1 — Title
**Multi-Agent Swarm**
*Get the best answer by comparing multiple AI perspectives*

### Slide 2 — Step 1: Open Swarm
**Click "Multi-Agent Swarm" in the sidebar**
- Or use `/swarm` command in chat
- Shows the agent selection and prompt input

### Slide 3 — Step 2: Enter Your Prompt
**Describe what you want multiple agents to work on**
- Example: "Compare approaches to building a real-time chat application"
- The prompt is sent to all selected agents simultaneously

### Slide 4 — Step 3: Select Agents
**Choose which agents participate**
- Brain: Deep reasoning and analysis
- Builder: Full-stack code generation
- Specs: Architecture and requirements
- Or use defaults for balanced coverage

### Slide 5 — Step 4: Review Results
**Compare outputs side by side**
- Each agent's response is shown in a card
- The judge agent picks the best one
- Click any card to expand the full response
- Export the winner to continue working

---

## Screenshot Guide

### Screenshot 1: Swarm Configuration
**What to capture**: The swarm configuration screen
**Description**: Shows the prompt input, agent selection checkboxes, and strategy options.

### Screenshot 2: Swarm Execution
**What to capture**: Multiple agents running simultaneously
**Description**: Shows the DAG view with agents executing in parallel, with progress indicators.

### Screenshot 3: Swarm Results
**What to capture**: The side-by-side comparison of agent outputs
**Description**: Shows multiple response cards with the winner highlighted, including the judge's reasoning.

---

# GUIDE 8: Knowledge & Memory

## Slide Deck

### Slide 1 — Title
**Knowledge & Memory**
*Your AI remembers key facts across all conversations*

### Slide 2 — Step 1: Open Memory
**Click "Memory" in the sidebar**
- See your knowledge base as a 3D graph
- Or use the list view for browsing

### Slide 3 — Step 2: Add Knowledge
**Multiple ways to add content**
- Conversations are automatically indexed
- Paste text directly
- Upload files (PDF, Word, text)
- Connect to Obsidian vault

### Slide 4 — Step 3: Search Your Knowledge
**Find relevant information**
- Use the search bar in the Memory pane
- Enable RAG in chat to ground AI responses
- Semantic search finds related content

### Slide 5 — Step 4: Use Memory in Chat
**Ground AI responses in your knowledge**
- Click the 🧠 Memory button in chat
- AI retrieves relevant memories before responding
- Responses are more accurate and personalized

---

## Screenshot Guide

### Screenshot 1: Memory Galaxy View
**What to capture**: The 3D memory graph visualization
**Description**: Shows memory nodes connected by relationships, with zoom and pan controls visible.

### Screenshot 2: Memory Search Results
**What to capture**: Search results in the memory pane
**Description**: Shows search query with matching memories listed, including relevance scores and snippets.

### Screenshot 3: RAG-Enhanced Chat
**What to capture**: A chat message with RAG enabled
**description**: Shows the 🧠 Memory button active, with the AI's response citing specific memories from the knowledge base.

---

# GUIDE 9: Create Custom Agents

## Slide Deck

### Slide 1 — Title
**Create Custom Agents**
*Build specialized AI assistants for your specific needs*

### Slide 2 — Step 1: Open Agent Panel
**Click the agent selector in the chat header**
- See built-in agents and your custom ones
- Click "+ Add Agent" to create new

### Slide 3 — Step 2: Define Your Agent
**Set up the agent's identity**
- Name: Descriptive name (e.g., "Security Reviewer")
- Model: Choose which AI model to use
- System Prompt: Define expertise and behavior
- Avatar: Pick an emoji for easy identification

### Slide 4 — Step 3: Write an Effective System Prompt
**Define the agent's expertise**
- Start with the role: "You are an expert..."
- Include specific instructions and constraints
- Define output format expectations
- Example: "You are a security code reviewer. Focus on SQL injection, XSS, and authentication vulnerabilities. Always provide CVE references and fix suggestions."

### Slide 5 — Step 4: Use Your Agent
**Switch agents in any conversation**
- Select from the dropdown in chat header
- Different agents can use different models
- Use Steering rules for persistent behavior changes
- Share agents with your team

---

## Screenshot Guide

### Screenshot 1: Agent List
**What to capture**: The agent selector dropdown
**Description**: Shows built-in agents (Direct AI Chat, Brain, Orchestrator, Builder) with custom agents listed below.

### Screenshot 2: Agent Creation Form
**What to capture**: The agent creation modal
**Description**: Shows all fields filled out with a sample agent configuration.

### Screenshot 3: Agent Conversation
**What to capture**: A conversation with a custom agent
**Description**: Shows the agent's avatar and name in the message header, with a specialized response.

---

# GUIDE 10: Evaluate Your AI Agent Quality

## Slide Deck

### Slide 1 — Title
**Evaluate Your AI Agent Quality**
*Measure and improve agent performance with automated evaluations*

### Slide 2 — Step 1: Open Eval Framework
**Click "Evaluation" in the sidebar**
- Under "Monitoring & Security" group
- See existing eval suites and results

### Slide 3 — Step 2: Create a Test Suite
**Define test cases for your agent**
- Input: The prompt to send
- Expected: What a good response looks like
- Assertions: Specific things to check
- Timeout: Maximum response time

### Slide 4 — Step 3: Run Evaluations
**Execute automated evaluations**
- Run against your agent
- Measure quality metrics (accuracy, completeness, safety)
- Compare results across different models
- Track improvements over time

### Slide 5 — Step 4: Analyze and Improve
**Use results to improve your agent**
- Identify weak areas from failed test cases
- Adjust system prompt based on results
- Compare different models' performance
- Set up automated regression testing

---

## Screenshot Guide

### Screenshot 1: Eval Suite List
**What to capture**: The eval framework dashboard
**Description**: Shows existing eval suites with pass rates, last run dates, and status indicators.

### Screenshot 2: Test Case Editor
**What to capture**: The test case creation form
**Description**: Shows fields for input, expected output, assertions, and timeout settings.

### Screenshot 3: Eval Results
**What to capture**: Evaluation results with pass/fail indicators
**Description**: Shows test cases with pass/fail status, response times, and detailed failure messages for failed cases.

---

# Additional Guides

## GUIDE 11: Settings & Configuration

### Screenshot Guide

#### Screenshot 1: Settings Overview
**What to capture**: The full Settings pane
**Description**: Shows the settings sidebar with tabs (Connect AI, Theme & Aesthetics, Navigation & Layout, AI Agents, Local Ollama, Storage & DB Backup).

#### Screenshot 2: AI Connection Setup
**What to capture**: The Connect AI tab
**Description**: Shows the connection paths (local, cloud, custom), the API key input, and the connection status.

#### Screenshot 3: Theme Selection
**What to capture**: The Theme & Aesthetics tab
**Description**: Shows theme options (Light, Dark, Auto), accent color picker, and font size controls.

---

## GUIDE 12: Command Palette (⌘K)

### Screenshot Guide

#### Screenshot 1: Command Palette Open
**What to capture**: The command palette modal
**Description**: Shows the search input with results below, including commands, agents, and global search results.

#### Screenshot 2: Search Results
**What to capture**: Search results with different categories
**Description**: Shows "Quick Commands", "Chat History", and "Global Search Matches" sections with icons and descriptions.

---

## GUIDE 13: Sidebar Navigation

### Screenshot Guide

#### Screenshot 1: Getting Started Group
**What to capture**: The expanded "Getting Started" sidebar group
**Description**: Shows Chat, Code Studio, Templates, Memory, Tasks, Settings with their icons and help tooltips.

#### Screenshot 2: Advanced Groups
**What to capture**: One advanced group expanded
**Description**: Shows "AI Tools" group with Multi-Agent Swarm, AI Operating Manual, Code Editor, etc.

#### Screenshot 3: Collapsed Sidebar
**What to capture**: The sidebar in collapsed state
**Description**: Shows only icons with hover tooltips visible.

---

## GUIDE 14: Drag & Drop

### Screenshot Guide

#### Screenshot 1: File Drop on Chat
**What to capture**: A file being dragged over the chat area
**Description**: Shows the dropzone overlay with "Drop text, code, data, PDF, or Word files to add them to this chat" message.

#### Screenshot 2: Attachment Tray
**What to capture**: Files in the attachment tray
**Description**: Shows file chips with icons, names, and remove buttons.

---

## GUIDE 15: One-Click Setup

### Screenshot Guide

#### Screenshot 1: Quick Setup Modal
**What to capture**: The one-click setup modal
**Description**: Shows the neural orb animation, backend detection status, and recommendation.

#### Screenshot 2: Ollama Detected
**What to capture**: The setup modal after detecting Ollama
**Description**: Shows "Ready! No API key needed" with the list of available models.

#### Screenshot 3: API Key Input
**What to capture**: The API key input in the setup modal
**Description**: Shows the password input field with "Connect" button and the OpenRouter key placeholder.

---

## GUIDE 16: Floating Action Button & Quick Actions

### Screenshot Guide

#### Screenshot 1: Floating Action Button
**What to capture**: The 💬 FAB in the bottom-right corner
**Description**: Shows the floating action button with hover state.

#### Screenshot 2: Quick Action Cards
**What to capture**: The quick action cards in the empty chat state
**Description**: Shows 4 cards: Build something, Research a topic, Improve my code, Start from template.
