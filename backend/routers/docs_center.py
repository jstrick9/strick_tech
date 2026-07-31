"""
Agentic OS — Documentation Center
Full in-app docs: quick-starts, feature reference, FAQ, video links, search.

Content is stored as structured JSON so the frontend can render it beautifully.
Supports: full-text search, contextual help (docs for current pane), categories,
          feedback rating (helpful / not helpful tracked in memory).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix='/api/docs', tags=['docs'])

# ── In-memory feedback store (lightweight — resets on restart, no DB needed) ──
_feedback: list[dict] = []  # [{doc_id, doc_type, helpful, ts}]

# ── Documentation content ──────────────────────────────────────────────────────
QUICK_STARTS = [
    {
        'id': 'qs_chat',
        'title': 'Chat with AI in 60 seconds',
        'icon': '💬',
        'time': '1 min',
        'level': 'beginner',
        'steps': [
            {
                'step': 1,
                'title': 'Open Chat',
                'desc': "Click 'Chat' in the left sidebar. It's the first item.",
                'tip': 'Keyboard shortcut: click the logo at top-left',
            },
            {
                'step': 2,
                'title': 'Add your API key',
                'desc': "Go to Settings → API Keys and paste your OpenRouter API key. It's free to get one at openrouter.ai",
                'tip': 'The key is stored encrypted on your machine — never sent anywhere else',
            },
            {
                'step': 3,
                'title': 'Pick a model',
                'desc': 'Click the model badge (top of chat) and choose from 10+ free and paid models',
                'tip': "Start with 'Llama 3.3 70B' (free) or 'Claude 3.5 Sonnet' (best quality)",
            },
            {
                'step': 4,
                'title': 'Start chatting!',
                'desc': 'Type anything and press Enter. Your AI is ready.',
                'tip': "Try: 'Explain what FastAPI is in simple terms'",
            },
        ],
        'video_url': '',  # TODO: Add walkthrough video
        'related': ['qs_agents', 'qs_workflow'],
    },
    {
        'id': 'qs_agents',
        'title': 'Create your first AI agent',
        'icon': '🤖',
        'time': '3 min',
        'level': 'beginner',
        'steps': [
            {
                'step': 1,
                'title': 'Go to Agents',
                'desc': "In the sidebar, find 'Agents' under your active agent pill at the top of chat. Click '+ New Agent'.",
                'tip': 'Or press ⌘/Ctrl + click on the avatar',
            },
            {
                'step': 2,
                'title': 'Name your agent',
                'desc': "Give it a name that reflects its purpose: 'Research Assistant', 'Python Helper', 'Writing Coach'",
                'tip': 'You can have unlimited agents with different specialties',
            },
            {
                'step': 3,
                'title': 'Write a system prompt',
                'desc': "Tell the agent its role: 'You are a Python expert. Always write clean, documented code with type hints.'",
                'tip': 'Be specific — the more focused the prompt, the better the results',
            },
            {
                'step': 4,
                'title': 'Pick a model and color',
                'desc': 'Choose which AI model powers this agent, and give it a color so you can spot it quickly',
                'tip': 'Different agents can use different models — use free models for simple tasks',
            },
            {
                'step': 5,
                'title': 'Save and chat!',
                'desc': 'Click Save, then select your new agent from the agent picker at the top of the chat pane',
                'tip': 'Switch agents mid-conversation anytime',
            },
        ],
        'video_url': '',  # TODO: Add walkthrough video
        'related': ['qs_chat', 'qs_workflow'],
    },
    {
        'id': 'qs_workflow',
        'title': 'Build your first workflow',
        'icon': '🗺️',
        'time': '5 min',
        'level': 'intermediate',
        'steps': [
            {
                'step': 1,
                'title': 'Open Workflow Builder',
                'desc': "Click '🗺️ Workflows' in the sidebar. You'll see 3 starter workflows already there.",
                'tip': "Start with 'Chat → Research → Summarize' as a template",
            },
            {
                'step': 2,
                'title': 'Add a node',
                'desc': 'Drag a node type from the left palette onto the canvas. Start with a Trigger node.',
                'tip': 'Trigger → Agent → Output is the simplest workflow',
            },
            {
                'step': 3,
                'title': 'Connect nodes',
                'desc': 'Drag from the right port (●) of one node to the left port of another to connect them',
                'tip': 'Hover over nodes to see connection points',
            },
            {
                'step': 4,
                'title': 'Configure the agent node',
                'desc': 'Click an Agent node → set which agent runs it and what prompt template to use. Use {{input}} for the workflow input.',
                'tip': 'You can chain multiple agents — output of one feeds the next',
            },
            {
                'step': 5,
                'title': 'Run it!',
                'desc': "Click '▶ Run' in the toolbar, type your input, and watch each node execute in real time",
                'tip': "Visit 'Replay' pane to scrub through the execution step-by-step afterward",
            },
        ],
        'video_url': '',  # TODO: Add walkthrough video
        'related': ['qs_agents', 'qs_specs'],
    },
    {
        'id': 'qs_specs',
        'title': 'Spec-driven development (plan before code)',
        'icon': '📋',
        'time': '10 min',
        'level': 'intermediate',
        'steps': [
            {
                'step': 1,
                'title': 'Open Spec Builder',
                'desc': "Click '📋 Spec Builder' in the sidebar",
                'tip': 'Like Kiro (AWS) — plan before you code',
            },
            {
                'step': 2,
                'title': 'Create a new spec',
                'desc': "Click '+ New Spec', give it a name like 'User Authentication System'",
                'tip': 'Be descriptive — the AI uses your description to generate requirements',
            },
            {
                'step': 3,
                'title': 'Describe what you want',
                'desc': 'Write a detailed description: what it does, who uses it, key behaviors',
                'tip': "More detail = better requirements. Include 'must haves' and 'nice to haves'",
            },
            {
                'step': 4,
                'title': 'Run Full Pipeline',
                'desc': "Click '🚀 Run Full Pipeline' — this generates Requirements → Design → Tasks automatically",
                'tip': 'Watch as the AI creates a proper requirements doc, architecture design, and task list',
            },
            {
                'step': 5,
                'title': 'Review and execute',
                'desc': "Switch to the Tasks tab to see the implementation plan. Click 'Execute' to have agents implement each task.",
                'tip': 'Tasks run in parallel waves — independent tasks execute simultaneously',
            },
        ],
        'video_url': '',  # TODO: Add walkthrough video
        'related': ['qs_workflow', 'qs_chat'],
    },
    {
        'id': 'qs_rag',
        'title': 'Build a document Q&A system',
        'icon': '📚',
        'time': '5 min',
        'level': 'intermediate',
        'steps': [
            {
                'step': 1,
                'title': 'Open RAG Builder',
                'desc': "Click '📚 RAG' in the sidebar (Enterprise feature)",
                'tip': 'RAG = Retrieval-Augmented Generation — AI answers from your documents',
            },
            {
                'step': 2,
                'title': 'Create a pipeline',
                'desc': "Click '+ New Pipeline', name it 'My Knowledge Base'",
                'tip': 'You can have multiple pipelines for different document sets',
            },
            {
                'step': 3,
                'title': 'Add documents',
                'desc': "Paste text content (from docs, manuals, notes) and click 'Add Document'",
                'tip': 'The AI automatically chunks and indexes the content',
            },
            {
                'step': 4,
                'title': 'Ask questions',
                'desc': 'Type a question and press Ask — the AI searches your documents and answers with citations',
                'tip': 'Answers reference which chunk they came from — no hallucination',
            },
        ],
        'video_url': '',  # TODO: Add walkthrough video
        'related': ['qs_chat', 'qs_agents'],
    },
    {
        'id': 'qs_studio',
        'title': 'Build an App with Studio',
        'icon': '⚡',
        'time': '3 min',
        'level': 'beginner',
        'steps': [
            {'step': 1, 'title': 'Open Studio', 'desc': "Click 'Code Studio' in the sidebar.", 'tip': 'Keyboard: ⌘2'},
            {'step': 2, 'title': 'Pick a template', 'desc': 'Choose from Templates pane or start blank.', 'tip': 'Try the SaaS Landing Page template'},
            {'step': 3, 'title': 'Edit with AI', 'desc': 'Type changes in the editor or ask AI to modify code.', 'tip': 'Use the AI chat panel inside Studio'},
            {'step': 4, 'title': 'Preview live', 'desc': 'See changes in the live preview panel instantly.', 'tip': 'Click the preview toggle button'},
        ],
        'video_url': '',
        'related': ['qs_chat', 'qs_workflow'],
    },
    {
        'id': 'qs_swarm',
        'title': 'Multi-Agent Swarm',
        'icon': '🌀',
        'time': '2 min',
        'level': 'intermediate',
        'steps': [
            {'step': 1, 'title': 'Open Swarm', 'desc': "Click 'Multi-Agent Swarm' in the sidebar.", 'tip': 'Or use /swarm command in chat'},
            {'step': 2, 'title': 'Enter your prompt', 'desc': 'Describe what you want multiple agents to work on.', 'tip': 'Try: Compare approaches to building a REST API'},
            {'step': 3, 'title': 'Select agents', 'desc': 'Choose which agents participate (or use defaults).', 'tip': 'Brain + Builder + Specs is a good combination'},
            {'step': 4, 'title': 'Review results', 'desc': 'Compare outputs side by side. The judge picks the best.', 'tip': 'Click any card to expand the full response'},
        ],
        'video_url': '',
        'related': ['qs_chat', 'qs_agents'],
    },
    {
        'id': 'qs_memory',
        'title': 'Knowledge & Memory',
        'icon': '🧠',
        'time': '2 min',
        'level': 'beginner',
        'steps': [
            {'step': 1, 'title': 'Open Memory', 'desc': "Click 'Memory' in the sidebar to see your knowledge base.", 'tip': 'All conversations are automatically indexed'},
            {'step': 2, 'title': 'Add knowledge', 'desc': 'Paste text, upload files, or let conversations auto-index.', 'tip': 'Use the Memory search in chat with the 🧠 button'},
            {'step': 3, 'title': 'Search your knowledge', 'desc': 'Type queries to find relevant memories across all conversations.', 'tip': 'Enable RAG in chat to ground AI responses in your knowledge'},
        ],
        'video_url': '',
        'related': ['qs_chat', 'qs_rag'],
    },
    {
        'id': 'qs_agents',
        'title': 'Create Custom Agents',
        'icon': '🤖',
        'time': '3 min',
        'level': 'intermediate',
        'steps': [
            {'step': 1, 'title': 'Open Agent panel', 'desc': 'Click the agent selector in the chat header.', 'tip': 'Or go to Settings → AI Agents'},
            {'step': 2, 'title': 'Create an agent', 'desc': 'Click + Add Agent and define its role, model, and system prompt.', 'tip': 'Start with a clear role description'},
            {'step': 3, 'title': 'Switch agents', 'desc': 'Select your agent from the dropdown in any chat.', 'tip': 'Different agents can use different models'},
            {'step': 4, 'title': 'Test and refine', 'desc': 'Chat with your agent and adjust its prompt as needed.', 'tip': 'Use Steering rules for persistent behavior changes'},
        ],
        'video_url': '',
        'related': ['qs_chat', 'qs_swarm'],
    },
    {
        'id': 'qs_eval',
        'title': 'Evaluate your AI agent quality',
        'icon': '🧮',
        'time': '5 min',
        'level': 'advanced',
        'steps': [
            {
                'step': 1,
                'title': 'Open Evals',
                'desc': "Click '🧮 Evals' in the sidebar (Enterprise feature)",
                'tip': 'Like DeepEval — score every agent response automatically',
            },
            {
                'step': 2,
                'title': 'Run a quick eval',
                'desc': "Click '▶ Quick Eval', enter the prompt you sent and the agent's response",
                'tip': 'The AI-judge scores faithfulness, hallucination, task completion, safety',
            },
            {
                'step': 3,
                'title': 'Review the score',
                'desc': "You'll get a 0-100 score with breakdown by metric and any detected issues",
                'tip': 'Below 70 = fail. Aim for 85+ in production',
            },
            {
                'step': 4,
                'title': 'Run Red Team tests',
                'desc': "Click '🔴 Red Team' to test if your agent is vulnerable to prompt injection, jailbreaks, PII extraction",
                'tip': "8 OWASP LLM Top 10 attacks — know your agent's security posture",
            },
        ],
        'video_url': '',  # TODO: Add walkthrough video
        'related': ['qs_agents', 'qs_specs'],
    },
]

FEATURE_DOCS: dict[str, dict] = {
    'chat': {
        'title': 'Chat',
        'icon': '💬',
        'tier': 'free',
        'summary': 'Chat with any AI model. Switch agents mid-conversation. Stream responses in real time.',
        'details': 'The Chat pane is the heart of Agentic OS. You can talk to any of your agents, switch models on the fly, and the conversation is saved automatically. Use @mentions to pull in files from your project.',
        'tips': [
            'Press ⌘↑ to access chat history',
            'Click the model badge to switch models without losing context',
            'Use /command shortcuts: /clear, /save, /export',
        ],
        'video_url': '',  # TODO: Add walkthrough video
    },
    'workflow': {
        'title': 'Workflow Builder',
        'icon': '🗺️',
        'tier': 'pro',
        'summary': 'Build n8n-style visual workflows that chain multiple AI agents together.',
        'details': 'The Workflow Builder lets you create automated pipelines by connecting nodes on a canvas. Drag nodes from the palette, connect them with edges, and run the workflow with a single click.',
        'tips': [
            '⌘S saves the workflow',
            'Use the ⊡ button to fit the canvas to screen',
            'Workflow history in the Replay pane',
        ],
        'video_url': '',  # TODO: Add walkthrough video
    },
    'specs': {
        'title': 'Spec Builder',
        'icon': '📋',
        'tier': 'pro',
        'summary': 'Like AWS Kiro — generate Requirements → Design → Tasks → Code from a plain English description.',
        'details': "Spec-driven development prevents 'vibe coding' drift. You describe a feature, and the AI generates: a Requirements doc (EARS notation), an Architecture Design, and a dependency-mapped Task list.",
        'tips': [
            'The more detail in your description, the better the requirements',
            'Wave execution runs independent tasks simultaneously',
        ],
        'video_url': '',  # TODO: Add walkthrough video
    },
    'evals': {
        'title': 'Agent Evals',
        'icon': '🧮',
        'tier': 'enterprise',
        'summary': 'DeepEval-level scoring: faithfulness, hallucination, task completion, safety, and red-team attacks.',
        'details': 'The Evals engine runs automated quality scores on every agent response. Use it to detect regressions, benchmark model changes, and red-team your agents with 8 OWASP LLM Top 10 attacks.',
        'tips': [
            'Run Quick Eval after every major prompt change',
            'Red Team before going to production',
            'Compare scores across agents in the Leaderboard',
        ],
        'video_url': '',  # TODO: Add walkthrough video
    },
    'bugbot': {
        'title': 'BugBot',
        'icon': '🐛',
        'tier': 'pro',
        'summary': 'AI code reviewer for diffs, files, and GitHub PRs. Like Cursor BugBot.',
        'details': 'BugBot reviews code for bugs, security issues, performance problems, and documentation gaps. Paste a diff, review your git changes, upload a file, or connect a GitHub PR URL.',
        'tips': [
            'Review before every commit',
            'GitHub PR review automatically posts a comment',
            'Feedback on reviews helps BugBot learn your standards',
        ],
        'video_url': '',  # TODO: Add walkthrough video
    },
    'rag': {
        'title': 'RAG Pipeline',
        'icon': '📚',
        'tier': 'enterprise',
        'summary': 'Build document Q&A systems with vector search and citations. No hallucination.',
        'details': 'The RAG Pipeline Builder lets you create document retrieval systems. Ingest any text, PDFs, or code; the system chunks, embeds, and indexes it. Ask questions and get cited answers.',
        'tips': [
            'Use chunk size 512 for most documents',
            'Add multiple pipelines for different knowledge bases',
            'Combine with steering files for project-aware AI',
        ],
        'video_url': '',  # TODO: Add walkthrough video
    },
    'arena': {
        'title': 'Arena Mode',
        'icon': '⚔️',
        'tier': 'pro',
        'summary': 'A/B test two AI models side-by-side. Vote on winners. ELO ratings build a personal leaderboard.',
        'details': 'Arena Mode sends the same prompt to two models simultaneously and streams both responses. Vote on which is better — ELO ratings update automatically. Over time you build a personal leaderboard.',
        'tips': [
            'Budget preset uses free models — zero cost',
            'Quality preset uses frontier models',
            'Let Auto-Judge score battles automatically to build the leaderboard faster',
        ],
        'video_url': '',  # TODO: Add walkthrough video
    },
    'memory': {
        'title': 'Memory / Galaxy',
        'icon': '🌌',
        'tier': 'pro',
        'summary': 'Persistent semantic memory across all conversations. The AI remembers key facts automatically.',
        'details': 'The Memory system stores important facts, decisions, and patterns from your conversations. The AI automatically retrieves relevant memories when answering questions, giving it long-term context.',
        'tips': [
            'Add memories manually from any chat message',
            'Search your memory bank with semantic search',
            'Export memories as markdown for backup',
        ],
        'video_url': '',  # TODO: Add walkthrough video
    },
    'websearch': {
        'title': 'Web Search',
        'icon': '🔎',
        'tier': 'pro',
        'summary': 'Ground AI answers with live web citations. Like Perplexity — free DuckDuckGo search.',
        'details': 'Web Search Grounding searches the web first, then has the AI answer with citations. No API key needed — powered by DuckDuckGo. Use Deep Research mode for comprehensive multi-query research reports.',
        'tips': [
            'Use Grounded AI for factual questions',
            'Deep Research generates 4+ queries and synthesizes a report',
            'Search history is saved for quick replay',
        ],
        'video_url': '',  # TODO: Add walkthrough video
    },
    'settings': {
        'title': 'Settings', 'icon': '⚙', 'tier': 'free',
        'summary': 'Connect AI providers, customize appearance, manage agents, and configure the platform.',
        'details': 'Connect OpenRouter or Ollama for AI, choose themes, manage agent personas, configure Ollama local server, and manage database backups.',
        'tips': ['Start with Connect AI tab to set up your first model', 'Use Simple/Power mode toggle to control sidebar complexity'],
        'video_url': '',
    },
    'studio': {
        'title': 'Code Studio', 'icon': '⚡', 'tier': 'free',
        'summary': 'Full-featured code editor with Monaco, live preview, file tree, and AI-assisted editing.',
        'details': 'Monaco editor, live preview, file tree, and AI chat in one workspace. Edit code with syntax highlighting, preview changes in real time, and ask AI to help write or refactor code. Includes full version history with a side-by-side diff view (⇄) for comparing any saved version against your current file before restoring.',
        'tips': ['Use ⌘2 to jump to Studio', 'The live preview updates as you type', 'Ask AI to modify code using the built-in chat panel', 'Click the version count in the status bar to browse history, preview, diff, or restore any past save'],
        'video_url': '',
    },
    'kanban': {
        'title': 'Task Board', 'icon': '✅', 'tier': 'free',
        'summary': 'Kanban-style task management with drag-and-drop columns.',
        'details': 'Track your work with a visual Kanban board. Drag tasks between To Do, In Progress, and Done columns. Create tasks with AI-generated descriptions and priorities.',
        'tips': ['Drag and drop tasks between columns', 'Use /task in chat to create tasks from conversation'],
        'video_url': '',
    },
    'galaxy': {
        'title': 'Memory Galaxy', 'icon': '🧠', 'tier': 'free',
        'summary': '3D visualization of your knowledge base and conversation memories.',
        'details': 'The Memory Galaxy shows all your saved memories and conversations as an interactive 3D graph. Search, explore connections, and manage your knowledge base visually.',
        'tips': ['Click nodes to expand details', 'Use the search bar to find specific memories', 'Zoom and pan with mouse wheel and drag'],
        'video_url': '',
    },
    'swarm': {
        'title': 'Multi-Agent Swarm', 'icon': '🌀', 'tier': 'pro',
        'summary': 'Run the same prompt through multiple AI agents simultaneously and compare results.',
        'details': 'Swarm sends your prompt to multiple agents at once, collects their responses, and a judge agent picks the best one. Great for complex problems where you want diverse perspectives.',
        'tips': ['Use /swarm command in chat for quick access', 'Compare 3-5 agents for best results', 'The DAG view shows agent execution flow'],
        'video_url': '',
    },
    'hierarchy': {
        'title': 'AI Context & Guidelines', 'icon': '🧭', 'tier': 'pro',
        'summary': 'Build universal business context, project-specific instructions, and coding/steering rules that guide every AI agent.',
        'details': 'AI Context & Guidelines lets you define universal Tier 1 business context, Tier 2 project-specific IVREN instructions, and freeform AI Guidelines (coding/architecture rules), all automatically injected into every agent conversation, swarm query, and specialized agent session.',
        'tips': ['Start with Tier 1: Universal Context about yourself and your work', 'Add Tier 2 for project-specific instructions', 'Use the AI Guidelines tab for coding/architecture rules that should apply to every AI-generated change', 'The interview wizard helps you build this step by step'],
        'video_url': '',
    },
    'templates': {
        'title': 'Template Gallery', 'icon': '📋', 'tier': 'free',
        'summary': 'One-click deploy production-ready project templates.',
        'details': 'Browse and deploy 14+ production-ready templates including SaaS landing pages, admin dashboards, todo apps, portfolios, chat apps, and AI-powered applications.',
        'tips': ['Click any template to preview it', 'One click to scaffold into your workspace', 'Customize templates in Studio after deployment'],
        'video_url': '',
    },
    'browser': {
        'title': 'Browser Agent', 'icon': '🌐', 'tier': 'pro',
        'summary': 'Automated browser control for web scraping, testing, and interaction.',
        'details': 'Controls a headless browser to navigate websites, fill forms, take screenshots, and extract data. Perfect for web scraping and automated testing.',
        'tips': ['Use Playwright for reliable browser automation', 'Screenshots are saved for each session', 'Supports multiple browser sessions'],
        'video_url': '',
    },
    'imagegen': {
        'title': 'Image Generator', 'icon': '🎨', 'tier': 'pro',
        'summary': 'Generate and edit images using AI models.',
        'details': 'Create images from text prompts, edit existing images, and manage your image gallery. Supports multiple AI image generation models.',
        'tips': ['Be descriptive in your prompts for better results', 'Use style modifiers like "photorealistic" or "cartoon"', 'Images are saved to your gallery automatically'],
        'video_url': '',
    },
    'prompts': {
        'title': 'Prompt Library', 'icon': '💡', 'tier': 'free',
        'summary': 'Save, organize, and share your best prompts.',
        'details': 'Build a library of effective prompts for different tasks. Organize by category, share with the community, and quickly insert prompts into any conversation.',
        'tips': ['Save frequently used prompts for quick access', 'Use variables in prompts for dynamic content', 'Share prompts with the marketplace'],
        'video_url': '',
    },
    'terminal': {
        'title': 'Terminal', 'icon': '💻', 'tier': 'pro',
        'summary': 'In-app terminal for running commands and scripts.',
        'details': 'Execute shell commands, run scripts, and manage your development environment without leaving the app.',
        'tips': ['Use Up/Down arrows for command history', 'Ctrl+C to cancel running commands', 'Commands run in a sandboxed environment'],
        'video_url': '',
    },
    'skills': {
        'title': 'Skills', 'icon': '⚡', 'tier': 'pro',
        'summary': 'Reusable AI skill modules for specific tasks.',
        'details': 'Pre-built AI modules for common tasks like code review, writing, analysis, and more. Install skills from the marketplace or create your own.',
        'tips': ['Browse the marketplace for community skills', 'Create custom skills for your specific workflow', 'Skills can be shared with the team'],
        'video_url': '',
    },
    'composer': {
        'title': 'Composer', 'icon': '✍', 'tier': 'pro',
        'summary': 'Multi-file AI agent for complex code generation across entire projects.',
        'details': 'Handles complex code generation tasks that span multiple files. Describe what you want to build, and the AI generates a complete implementation.',
        'tips': ['Describe the full feature you want to build', 'Review generated files before applying', 'Use with specs for structured development'],
        'video_url': '',
    },
    'pipeline': {
        'title': 'Pipelines', 'icon': '⎈', 'tier': 'pro',
        'summary': 'Automated CI/CD-style pipelines for AI workflows.',
        'details': 'Build automated pipelines that chain multiple AI operations together. Trigger on events, schedule runs, and monitor pipeline health.',
        'tips': ['Start with a simple 2-step pipeline', 'Use templates for common pipeline patterns', 'Monitor pipeline health in the dashboard'],
        'video_url': '',
    },
    'github': {
        'title': 'GitHub', 'icon': '🐙', 'tier': 'pro',
        'summary': 'GitHub integration for repos, issues, PRs, and automated workflows.',
        'details': 'Connect your GitHub account to manage repositories, create issues, review pull requests, and trigger GitHub Actions workflows.',
        'tips': ['Connect your GitHub token in Settings', 'Create issues from chat conversations', 'Review PRs with AI assistance'],
        'video_url': '',
    },
    'deploy': {
        'title': 'Deploy', 'icon': '🚀', 'tier': 'pro',
        'summary': 'One-click deployment to major cloud platforms.',
        'details': 'Deploy your applications to AWS, Vercel, Netlify, and other cloud platforms with one click.',
        'tips': ['Connect your cloud provider credentials', 'Use templates for quick deployment', 'Monitor deployment status in real time'],
        'video_url': '',
    },
    'dbstudio': {
        'title': 'Database', 'icon': '🗄', 'tier': 'pro',
        'summary': 'Visual database management and query interface.',
        'details': 'Browse tables, run queries, and manage your database schema visually. Supports SQLite.',
        'tips': ['Use the query editor for custom SQL', 'Browse table data with pagination', 'Export query results to CSV'],
        'video_url': '',
    },
    'workspaces': {
        'title': 'Workspaces', 'icon': '📂', 'tier': 'pro',
        'summary': 'Manage multiple project workspaces and switch between them.',
        'details': 'Organize your work into separate workspaces. Each workspace has its own files, settings, and conversation history.',
        'tips': ['Create a workspace for each project', 'Switch workspaces using the sidebar', 'Export/import workspaces for backup'],
        'video_url': '',
    },
    'plugins': {
        'title': 'Plugins', 'icon': '🧩', 'tier': 'pro',
        'summary': 'Extend the platform with custom plugins and integrations.',
        'details': 'Install plugins from the marketplace or create your own. Plugins add new features, integrations, and capabilities.',
        'tips': ['Browse the marketplace for community plugins', 'Create custom plugins with the Plugin SDK', 'Manage installed plugins in Settings'],
        'video_url': '',
    },
    'supervisor': {
        'title': 'Supervisor', 'icon': '🎯', 'tier': 'pro',
        'summary': 'Hierarchical agent orchestration for complex multi-step tasks.',
        'details': 'Manages complex tasks by breaking them into subtasks, assigning them to specialized agents, and coordinating results.',
        'tips': ['Use for tasks that require multiple specialized skills', 'Monitor progress in the DAG view', 'Review and approve agent outputs'],
        'video_url': '',
    },
    'goals': {
        'title': 'Goals', 'icon': '🎯', 'tier': 'pro',
        'summary': 'Goal decomposition, tracking, and progress monitoring.',
        'details': 'Set high-level goals and let the AI decompose them into actionable tasks. Track progress, manage milestones, and get automated updates.',
        'tips': ['Break large goals into smaller milestones', 'Use the scoring system to track progress', 'Connect goals to workflows for automation'],
        'video_url': '',
    },
    'connectors': {
        'title': 'Integrations', 'icon': '🔗', 'tier': 'pro',
        'summary': 'Connect to Slack, Jira, GitHub, Email, Notion, Salesforce, and custom APIs.',
        'details': 'The connector framework lets you integrate with external services. Send messages, create issues, manage documents, and automate workflows.',
        'tips': ['Configure credentials in Settings', 'Test connections before using in workflows', 'Use the connector SDK for custom integrations'],
        'video_url': '',
    },
    'mcp': {
        'title': 'Tool Connections', 'icon': '🔧', 'tier': 'pro',
        'summary': 'Model Context Protocol tool management and configuration.',
        'details': 'Manage MCP tools that extend AI capabilities. Configure tool schemas, validate inputs, and monitor tool usage.',
        'tips': ['Add tools via the tool registry', 'Test tools before using in production', 'Monitor tool usage in the dashboard'],
        'video_url': '',
    },
    'mcp-gateway': {
        'title': 'Gateway', 'icon': '🚪', 'tier': 'pro',
        'summary': 'Policy engine for controlling AI tool access and permissions.',
        'details': 'Enforces policies for tool access, rate limiting, and permission management. Control which agents can use which tools.',
        'tips': ['Create policies for sensitive tools', 'Use the simulator to test policies', 'Monitor policy enforcement in the dashboard'],
        'video_url': '',
    },
    'a2a': {
        'title': 'Agent Network', 'icon': '🌐', 'tier': 'enterprise',
        'summary': 'Agent-to-agent communication network for distributed AI workflows.',
        'details': 'Enables agents to communicate directly with each other, delegate tasks, and coordinate across distributed systems.',
        'tips': ['Register agents in the network', 'Use delegation for complex multi-agent tasks', 'Monitor network activity in the dashboard'],
        'video_url': '',
    },
    'agent-identity': {
        'title': 'Agent Identity', 'icon': '🪪', 'tier': 'enterprise',
        'summary': 'Manage agent identities, tokens, and access permissions.',
        'details': 'Each agent has a unique identity with associated tokens and permissions. Manage agent access to tools, data, and external services.',
        'tips': ['Provision identities before deploying agents', 'Use tokens for secure agent-to-agent communication', 'Revoke tokens when agents are decommissioned'],
        'video_url': '',
    },
    'hitl': {
        'title': 'Review Queue', 'icon': '👁', 'tier': 'enterprise',
        'summary': 'Human-in-the-Loop approval queue for high-risk agent actions.',
        'details': 'Intercepts high-risk agent actions and requires human approval before execution. Configure which actions require review.',
        'tips': ['Enable HITL for sensitive operations', 'Review and approve/reject actions quickly', 'Set up notifications for pending reviews'],
        'video_url': '',
    },
    'fusion': {
        'title': 'Model Fusion', 'icon': '🔀', 'tier': 'pro',
        'summary': 'Combine multiple AI models for better results.',
        'details': 'Routes requests to the best model for each task, combines outputs from multiple models, and optimizes for cost and quality.',
        'tips': ['Use fusion for complex tasks that benefit from multiple perspectives', 'Configure model priorities based on task type', 'Monitor fusion performance in the dashboard'],
        'video_url': '',
    },
    'loops': {
        'title': 'Autonomous Loops', 'icon': '♾', 'tier': 'pro',
        'summary': 'Set up recurring AI tasks that run automatically on schedule.',
        'details': 'Run AI tasks on a schedule. Set up daily standups, periodic code reviews, automated research, or any recurring task.',
        'tips': ['Start with simple daily tasks', 'Use adaptive intervals for efficiency', 'Monitor loop health in the dashboard'],
        'video_url': '',
    },
    'replay': {
        'title': 'Execution Replay', 'icon': '⟲', 'tier': 'pro',
        'summary': 'Replay and analyze past agent executions.',
        'details': 'Record and replay agent executions for debugging, training, and analysis. Step through execution traces.',
        'tips': ['Record important executions for later review', 'Use replay for debugging complex workflows', 'Share replays with team members'],
        'video_url': '',
    },
    'collabedit': {
        'title': 'Collaborative Edit', 'icon': '👥', 'tier': 'enterprise',
        'summary': 'Real-time collaborative code editing with multiple participants.',
        'details': 'Edit code in real time with multiple participants. See cursors, changes, and comments from all collaborators.',
        'tips': ['Share the session URL with collaborators', 'Use comments for async feedback', 'Changes are synced in real time'],
        'video_url': '',
    },
    'dashboard': {
        'title': 'Dashboard', 'icon': '📊', 'tier': 'pro',
        'summary': 'Overview of platform activity, metrics, and health.',
        'details': 'High-level overview of platform usage, including conversation metrics, agent performance, cost tracking, and system health.',
        'tips': ['Check the dashboard for a quick status overview', 'Use metrics to optimize your workflow', 'Export reports for team review'],
        'video_url': '',
    },
    'audit-log': {
        'title': 'Audit Log', 'icon': '📝', 'tier': 'enterprise',
        'summary': 'Immutable audit trail of all platform actions and changes.',
        'details': 'Every action is recorded in the immutable audit log. Track who did what, when, and why. Essential for compliance.',
        'tips': ['Use the audit log for compliance reporting', 'Filter by action type for specific events', 'Export audit data for external analysis'],
        'video_url': '',
    },
    'leaderboard': {
        'title': 'Leaderboard', 'icon': '🏆', 'tier': 'pro',
        'summary': 'Agent performance rankings and comparison metrics.',
        'details': 'Track and compare agent performance across different metrics. See which agents perform best for different task types.',
        'tips': ['Use the leaderboard to select the best agent for each task', 'Track performance over time', 'Set up automated benchmarking'],
        'video_url': '',
    },
    'agent-monitor': {
        'title': 'Live Monitor', 'icon': '📡', 'tier': 'enterprise',
        'summary': 'Real-time monitoring of agent activity and performance.',
        'details': 'Monitor all agent activity in real time. See active conversations, resource usage, error rates, and performance metrics.',
        'tips': ['Use the live monitor for real-time oversight', 'Set up alerts for performance anomalies', 'Monitor resource usage to optimize costs'],
        'video_url': '',
    },
    'finops': {
        'title': 'Cost Tracking', 'icon': '💰', 'tier': 'enterprise',
        'summary': 'Track and optimize AI spending across agents and models.',
        'details': 'Monitor your AI spending in real time. Set budgets, track costs per agent and model, and optimize for cost efficiency.',
        'tips': ['Set budget alerts to avoid overspending', 'Compare costs across different models', 'Use the cost heatmap to identify expensive operations'],
        'video_url': '',
    },
    'eval-framework': {
        'title': 'Evaluation', 'icon': '🧪', 'tier': 'enterprise',
        'summary': 'Automated evaluation framework for agent quality assurance.',
        'details': 'Run automated evaluations on agent outputs. Define test suites, measure quality metrics, and track improvements over time.',
        'tips': ['Create test suites for your most important workflows', 'Run evaluations after prompt changes', 'Compare evaluation results across model versions'],
        'video_url': '',
    },
    'observability': {
        'title': 'Observability', 'icon': '🔭', 'tier': 'enterprise',
        'summary': 'Deep visibility into platform internals and agent behavior.',
        'details': 'Get deep visibility into how the platform and agents work internally. Trace requests, monitor performance, and debug issues.',
        'tips': ['Use traces to debug complex workflows', 'Monitor key metrics for performance optimization', 'Set up alerts for critical events'],
        'video_url': '',
    },
    'health': {
        'title': 'Health', 'icon': '💚', 'tier': 'free',
        'summary': 'System health monitoring and diagnostics.',
        'details': 'Check the health of all platform components including the database, AI connections, and external services.',
        'tips': ['Check health status before reporting issues', 'Use diagnostics to identify bottlenecks', 'Monitor resource usage trends'],
        'video_url': '',
    },
    'profiler': {
        'title': 'Profiler', 'icon': '📈', 'tier': 'pro',
        'summary': 'Performance profiling and optimization for agents and endpoints.',
        'details': 'Profile agent performance and API endpoints to identify bottlenecks. Get detailed timing, resource usage, and optimization recommendations.',
        'tips': ['Profile slow operations to identify bottlenecks', 'Compare performance before and after changes', 'Use the flamegraph to visualize hot paths'],
        'video_url': '',
    },
    'secrets': {
        'title': 'Secrets Vault', 'icon': '🔐', 'tier': 'pro',
        'summary': 'Encrypted storage for API keys, tokens, and sensitive configuration.',
        'details': 'Store all your sensitive credentials in the encrypted vault. API keys, tokens, and passwords are encrypted at rest.',
        'tips': ['Store all API keys in the vault', 'Use the vault for secure credential management', 'Rotate keys regularly for security'],
        'video_url': '',
    },
    'pqc': {
        'title': 'Encryption', 'icon': '🛡', 'tier': 'enterprise',
        'summary': 'Post-quantum cryptography vault for future-proof security.',
        'details': 'Post-quantum encryption ensures your data remains secure even against quantum computing attacks.',
        'tips': ['Enable PQC for sensitive data', 'Manage encryption keys in the vault', 'Export certificates for external use'],
        'video_url': '',
    },
    'obsidian': {
        'title': 'Obsidian Sync', 'icon': '📝', 'tier': 'pro',
        'summary': 'Sync your Obsidian vault with the platform knowledge base.',
        'details': 'Connect your Obsidian vault to automatically sync notes, documents, and knowledge with the platform.',
        'tips': ['Configure the Obsidian vault path', 'Sync happens automatically on changes', 'Use Obsidian notes as context for AI conversations'],
        'video_url': '',
    },
    'webhooks': {
        'title': 'Webhooks', 'icon': '🔔', 'tier': 'pro',
        'summary': 'Event-driven webhooks for automated workflows.',
        'details': 'Set up webhooks to trigger automated workflows when specific events occur. Send notifications, trigger external services.',
        'tips': ['Create webhooks for important events', 'Test webhooks before deploying', 'Use the webhook viewer to monitor activity'],
        'video_url': '',
    },
    'integrations': {
        'title': 'Docs & Integrations', 'icon': '🔗', 'tier': 'pro',
        'summary': 'Documentation browser and integration marketplace.',
        'details': 'Browse and install integrations for popular services. Access documentation for all available integrations.',
        'tips': ['Browse the marketplace for new integrations', 'Read the docs before configuring', 'Test integrations before using in production'],
        'video_url': '',
    },
    'knowledge-graph': {
        'title': 'Knowledge Graph', 'icon': '🕸', 'tier': 'enterprise',
        'summary': 'Visual knowledge graph for exploring relationships in your data.',
        'details': 'Build and explore a knowledge graph of your data. Visualize relationships between concepts, entities, and documents.',
        'tips': ['Start with a seed concept and expand', 'Use the graph to discover hidden connections', 'Export graph data for external analysis'],
        'video_url': '',
    },
    'hooks': {
        'title': 'Event Hooks', 'icon': '⚡', 'tier': 'pro',
        'summary': 'Custom event handlers for platform automation.',
        'details': 'Create custom event handlers that trigger when specific platform events occur. Automate workflows and integrate with external systems.',
        'tips': ['Create hooks for important events', 'Test hooks in a safe environment', 'Monitor hook execution in the dashboard'],
        'video_url': '',
    },
    'codeindex': {
        'title': 'Code Index', 'icon': '🔍', 'tier': 'pro',
        'summary': 'Code search and symbol index for your projects.',
        'details': 'Index your codebase for fast search and symbol lookup. Find functions, classes, and references across your entire project.',
        'tips': ['Index your project before searching', 'Use symbol search for quick navigation', 'Find unused code with the dead code detector'],
        'video_url': '',
    },
    'codesearch': {
        'title': 'Code Search', 'icon': '⌕', 'tier': 'pro',
        'summary': 'Fast full-text search across your entire codebase.',
        'details': 'Search your codebase with fast full-text search. Find functions, variables, comments, and any text across all files.',
        'tips': ['Use regex for advanced search patterns', 'Filter by file type for faster results', 'Search across multiple projects'],
        'video_url': '',
    },
    'gitai': {
        'title': 'Git Assistant', 'icon': '⎇', 'tier': 'pro',
        'summary': 'AI-powered git operations and code review.',
        'details': 'Get AI assistance for git operations including commit messages, code review, branch management, and merge conflict resolution.',
        'tips': ['Use AI to generate commit messages', 'Review diffs before committing', 'Get AI suggestions for merge conflicts'],
        'video_url': '',
    },
    'testgen': {
        'title': 'Test Generator', 'icon': '🧪', 'tier': 'pro',
        'summary': 'AI-powered test case generation for your code.',
        'details': 'Automatically generate test cases for your functions and modules. Supports unit tests, integration tests, and edge case detection.',
        'tips': ['Generate tests for new functions', 'Review generated tests for accuracy', 'Run tests after generation to verify'],
        'video_url': '',
    },
    'marketplace': {
        'title': 'Marketplace', 'icon': '🛒', 'tier': 'free',
        'summary': 'Browse and install plugins, templates, and extensions.',
        'details': 'The Marketplace is your one-stop shop for extending the platform. Browse plugins, templates, skills, and integrations.',
        'tips': ['Browse by category for easier discovery', 'Read reviews before installing', 'Share your creations with the community'],
        'video_url': '',
    },
    'pluginsdk': {
        'title': 'Plugin SDK', 'icon': '🔧', 'tier': 'pro',
        'summary': 'Developer toolkit for creating custom plugins.',
        'details': 'The Plugin SDK provides everything you need to create custom plugins. Includes APIs, templates, and documentation.',
        'tips': ['Start with the plugin template', 'Test plugins in the sandbox environment', 'Publish plugins to the marketplace'],
        'video_url': '',
    },
    'multitab': {
        'title': 'Multi-Preview', 'icon': '◫', 'tier': 'pro',
        'summary': 'Side-by-side preview of multiple panes and documents.',
        'details': 'View multiple panes side by side for comparison and multitasking. Arrange your workspace for maximum productivity.',
        'tips': ['Drag panes to arrange your layout', 'Save layouts for different workflows', 'Use split view for code + preview'],
        'video_url': '',
    },
    'control': {
        'title': 'Control Tower', 'icon': '🎛', 'tier': 'enterprise',
        'summary': 'Centralized management and monitoring of the entire platform.',
        'details': 'Provides a centralized view of all platform components. Monitor health, manage configurations, and control access.',
        'tips': ['Use the Control Tower for platform-wide operations', 'Monitor all components from one view', 'Manage access control and permissions'],
        'video_url': '',
    },
    'system': {
        'title': 'System', 'icon': '⚙', 'tier': 'pro',
        'summary': 'System configuration, monitoring, and maintenance.',
        'details': 'Configure system settings, monitor resource usage, and perform maintenance tasks. Includes database management and diagnostics.',
        'tips': ['Check system health regularly', 'Use diagnostics for troubleshooting', 'Manage database backups'],
        'video_url': '',
    },
    'ambient': {
        'title': 'Ambient Mode', 'icon': '🌙', 'tier': 'pro',
        'summary': 'Background AI monitoring and proactive assistance.',
        'details': 'Runs in the background, monitoring your work and providing proactive assistance. Get suggestions and alerts.',
        'tips': ['Enable Ambient Mode for proactive assistance', 'Configure which events trigger notifications', 'Use Ambient for background monitoring'],
        'video_url': '',
    },
    'finetune': {
        'title': 'Fine-Tuning', 'icon': '🧪', 'tier': 'enterprise',
        'summary': 'Fine-tune AI models on your specific data and use cases.',
        'details': 'Fine-tune models to better understand your domain, coding style, and specific requirements.',
        'tips': ['Start with a small dataset for testing', 'Monitor training progress', 'Evaluate fine-tuned models before deploying'],
        'video_url': '',
    },
    'docs': {
        'title': 'Docs & Help', 'icon': '📖', 'tier': 'free',
        'summary': 'In-app documentation, quick starts, FAQ, and contextual help.',
        'details': 'Access all documentation directly inside the app. Quick start guides, FAQ, and contextual help for the current pane.',
        'tips': ['Use the search bar to find specific topics', 'Quick starts provide step-by-step guides', 'Rate docs to help improve them'],
        'video_url': '',
    },
    'notifications': {
        'title': 'Notifications', 'icon': '🔔', 'tier': 'free',
        'summary': 'Platform notifications and alerts.',
        'details': 'View all platform notifications including agent activity, system alerts, and task completions.',
        'tips': ['Check notifications regularly for important updates', 'Configure notification preferences in Settings', 'Mark notifications as read to keep the list clean'],
        'video_url': '',
    },
}

FAQ = [
    {
        'q': 'Do I need an OpenRouter API key?',
        'a': 'For chat and agent features, yes. Get a free key at openrouter.ai — many models are free with no credit card required. The key is stored encrypted on your machine.',
        'tags': ['setup', 'api'],
    },
    {
        'q': 'Is my data private?',
        'a': 'Yes. Agentic OS is local-first. Your code, conversations, and documents stay on your machine. Only the text you send to AI models goes to the model provider — never to us.',
        'tags': ['privacy', 'security'],
    },
    {
        'q': "What's the difference between Simple Mode and Power Mode?",
        'a': 'Simple Mode shows only the 6 core features in a clean layout — perfect for getting started. Power Mode unlocks the full sidebar with all 50+ panes. Switch anytime in Settings → Appearance.',
        'tags': ['ui', 'modes'],
    },
    {
        'q': 'How do I add my own AI models?',
        'a': 'Go to Settings → API Keys. Add your OpenRouter key for 100+ models, or your Ollama URL for local models. You can also add direct Anthropic, OpenAI, or Google API keys.',
        'tags': ['models', 'setup'],
    },
    {
        'q': 'Can I use this offline?',
        'a': 'Basic features work offline (docs, kanban, saved conversations). AI features require internet to reach model providers. Ollama gives you fully offline local AI if installed.',
        'tags': ['offline', 'privacy'],
    },
    {
        'q': 'What features are available?',
        'a': 'All features are available in the full platform. Your data stays on your machine — conversations, agents, and projects are always accessible.',
        'tags': ['trial', 'pricing'],
    },
    {
        'q': 'How do I back up my data?',
        'a': "Go to Settings → click 'Backup Database'. This creates a timestamped .db file in memory/. You can also export your workspace as a ZIP from the Workspaces pane.",
        'tags': ['backup', 'data'],
    },
    {
        'q': 'Can multiple people use this?',
        'a': 'The platform supports single-user operation. For team use, deploy with Docker and configure shared workspaces and role-based access in Settings.',
        'tags': ['team', 'enterprise'],
    },
    {
        'q': 'How do I check my license status?',
        'a': "Go to Settings → License to see your current tier and available features. All core features are available in the standard license.",
        'tags': ['trial', 'dev'],
    },
    {
        'q': "What's a Steering File?",
        'a': "Steering files (now called AI Guidelines) are like .cursorrules or Kiro's .kiro/steering/ — freeform rule files that get injected into every AI prompt so the AI always knows your tech stack, coding style, and project context. Go to 🧭 AI Context & Guidelines → the AI Guidelines tab to manage them.",
        'tags': ['steering', 'agents'],
    },
    {
        'q': 'How does the Workflow Builder work?',
        'a': 'Drag nodes from the palette onto the canvas, connect them with edges, and run. Each node is a step: Trigger → Agent → Condition → Output. Agents chain their outputs as inputs to the next node.',
        'tags': ['workflow', 'agents'],
    },
    {
        'q': 'What is Spec-Driven Development?',
        'a': 'Instead of jumping straight to code, Spec Builder generates Requirements, Design, and Tasks from your description first. Like AWS Kiro — forces planning before coding, prevents drift.',
        'tags': ['specs', 'workflow'],
    },
]

KEYBOARD_SHORTCUTS = [
    {'key': '⌘K', 'desc': 'Open command palette / global search'},
    {'key': '⌘P', 'desc': 'Code search'},
    {'key': '⌘L', 'desc': 'Prompt library'},
    {'key': '⌘U', 'desc': 'Share / invite to collaboration'},
    {'key': '⌘\\', 'desc': 'Toggle sidebar'},
    {'key': '⌘,', 'desc': 'Open settings'},
    {'key': '⌘/', 'desc': 'Open documentation center'},
    {'key': '⌘⇧W', 'desc': 'Open Workflow Builder'},
    {'key': '⌘⇧P', 'desc': 'Open Profiler'},
    {'key': '⌘⇧B', 'desc': 'Open BugBot'},
    {'key': '⌘⇧E', 'desc': 'Open Evals'},
    {'key': '⌘⇧F', 'desc': 'Open Model Fusion'},
    {'key': '⌘⇧M', 'desc': 'Open Marketplace'},
    {'key': '⌘⇧R', 'desc': 'Open Replay'},
    {'key': 'Ctrl+Shift+V', 'desc': 'Toggle Voice Coding'},
    {'key': '⌘T', 'desc': 'New tab (Multi-tab preview)'},
    {'key': '⌘W', 'desc': 'Close current tab'},
    {'key': '⌘⇧I', 'desc': 'Open user profile panel'},
]


# ── REST endpoints ──────────────────────────────────────────────────────────────


@router.get('/quick-starts')
def get_quick_starts(level: str = ''):
    """Retrieve and return get quick starts."""
    qs = QUICK_STARTS
    if level:
        qs = [q for q in qs if q.get('level', '') == level]
    return {'quick_starts': qs, 'count': len(qs)}


@router.get('/quick-starts/{qs_id}')
def get_quick_start(qs_id: str):
    """Retrieve and return get quick start."""
    qs = next((q for q in QUICK_STARTS if q['id'] == qs_id), None)
    if not qs:
        raise HTTPException(status_code=404, detail=f"Quick-start '{qs_id}' not found")
    return qs


@router.get('/features')
def list_feature_docs(tier: str = ''):
    """Retrieve and return list feature docs."""
    docs = [{'id': k, **v} for k, v in FEATURE_DOCS.items()]
    if tier:
        docs = [d for d in docs if d.get('tier', '') == tier]
    return {'features': docs, 'count': len(docs)}


@router.get('/features/{pane_id}')
def get_feature_doc(pane_id: str):
    """Retrieve and return get feature doc."""
    doc = FEATURE_DOCS.get(pane_id)
    if not doc:
        # Return a stub rather than 404 so contextual help always works
        return {
            'id': pane_id,
            'title': pane_id.replace('-', ' ').title(),
            'icon': '🔧',
            'tier': 'pro',
            'summary': f'The {pane_id} feature. Documentation coming soon.',
            'details': 'This feature is part of the Agentic OS platform. Check back for detailed documentation.',
            'tips': ['Explore the feature by clicking around', 'Hover over elements for tooltips'],
            'video_url': '',  # TODO: Add walkthrough video
        }
    return {'id': pane_id, **doc}


@router.get('/faq')
def get_faq(q: str = ''):
    """Retrieve and return get faq."""
    faq = FAQ
    if q:
        qlow = q.lower()
        faq = [
            f
            for f in FAQ
            if qlow in f['q'].lower() or qlow in f['a'].lower() or any(qlow in t for t in f.get('tags', []))
        ]
    return {'faq': faq, 'count': len(faq)}


@router.get('/shortcuts')
def get_shortcuts():
    """Retrieve and return get shortcuts."""
    return {'shortcuts': KEYBOARD_SHORTCUTS, 'count': len(KEYBOARD_SHORTCUTS)}


@router.get('/search')
def search_docs(q: str = '', limit: int = 20):
    """Full-text search across all docs content."""
    limit = max(1, min(int(limit), 50))  # clamp to sane range
    if not q:
        return {'results': [], 'query': q, 'count': 0}
    qlow = q.lower()
    results: list[dict] = []

    # Search quick-starts
    for qs in QUICK_STARTS:
        score = 0
        if qlow in qs['title'].lower():
            score += 10
        for step in qs.get('steps', []):
            if qlow in step.get('title', '').lower():
                score += 5
            if qlow in step.get('desc', '').lower():
                score += 2
        if score > 0:
            results.append(
                {
                    'type': 'quickstart',
                    'score': score,
                    'title': qs['title'],
                    'icon': qs['icon'],
                    'id': qs['id'],
                    'level': qs['level'],
                }
            )

    # Search feature docs
    for pane_id, doc in FEATURE_DOCS.items():
        score = 0
        if qlow in doc.get('title', '').lower():
            score += 10
        if qlow in doc.get('summary', '').lower():
            score += 6
        if qlow in doc.get('details', '').lower():
            score += 3
        for tip in doc.get('tips', []):
            if qlow in tip.lower():
                score += 2
        if score > 0:
            results.append(
                {
                    'type': 'feature',
                    'score': score,
                    'title': doc['title'],
                    'icon': doc.get('icon', '🔧'),
                    'id': pane_id,
                    'tier': doc.get('tier', 'pro'),
                }
            )

    # Search FAQ
    for i, f in enumerate(FAQ):
        score = 0
        if qlow in f['q'].lower():
            score += 10
        if qlow in f['a'].lower():
            score += 4
        if any(qlow in t for t in f.get('tags', [])):
            score += 3
        if score > 0:
            results.append(
                {'type': 'faq', 'score': score, 'title': f['q'], 'id': str(i), 'answer_preview': f['a'][:120]}
            )

    # Search shortcuts
    for s in KEYBOARD_SHORTCUTS:
        if qlow in s['desc'].lower():
            results.append({'type': 'shortcut', 'score': 5, 'title': s['desc'], 'id': s['key'], 'shortcut': s['key']})

    results.sort(key=lambda x: x['score'], reverse=True)
    trimmed = results[:limit]
    return {'results': trimmed, 'count': len(results), 'shown': len(trimmed), 'query': q}


@router.get('/contextual/{pane_id}')
def contextual_help(pane_id: str):
    """Get contextual help content for the currently active pane."""
    try:
        doc = FEATURE_DOCS.get(pane_id)
        if doc:
            doc = {'id': pane_id, **doc}

        related_qs = [
            qs
            for qs in QUICK_STARTS
            if pane_id in qs.get('related', []) or any(pane_id in s.get('desc', '') for s in qs.get('steps', []))
        ]

        faq_matches = [f for f in FAQ if pane_id in ' '.join(f.get('tags', [])) or pane_id in f['q'].lower()][:3]

        shortcut_matches = [s for s in KEYBOARD_SHORTCUTS if pane_id in s['desc'].lower()]

        return {
            'pane': pane_id,
            'doc': doc,
            'quick_starts': related_qs[:2],
            'faq': faq_matches,
            'shortcuts': shortcut_matches,
        }
    except Exception as exc:
        return {'pane': pane_id, 'doc': None, 'quick_starts': [], 'faq': [], 'shortcuts': [], 'error': str(exc)}


@router.post('/feedback')
async def submit_feedback(req: Request):
    """Rate a doc as helpful or not helpful."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        return {'ok': False, 'error': 'Invalid JSON body'}

    doc_id = (body.get('doc_id') or '').strip()[:100]
    doc_type = (body.get('doc_type') or 'feature').strip()[:20]
    helpful = bool(body.get('helpful', True))

    if not doc_id:
        return {'ok': False, 'error': 'doc_id required'}
    if doc_type not in {'feature', 'quickstart', 'faq', 'shortcut'}:
        doc_type = 'feature'

    import time

    _feedback.append({'doc_id': doc_id, 'doc_type': doc_type, 'helpful': helpful, 'ts': int(time.time())})

    # Keep last 1000 feedback items in memory
    if len(_feedback) > 1000:
        _feedback.pop(0)

    return {'ok': True, 'total_feedback': len(_feedback)}


@router.get('/feedback/summary')
def feedback_summary():
    """Return aggregated feedback counts."""
    counts: dict[str, dict] = {}
    for item in _feedback:
        key = f'{item["doc_type"]}:{item["doc_id"]}'
        if key not in counts:
            counts[key] = {'doc_id': item['doc_id'], 'doc_type': item['doc_type'], 'helpful': 0, 'not_helpful': 0}
        if item['helpful']:
            counts[key]['helpful'] += 1
        else:
            counts[key]['not_helpful'] += 1
    return {'feedback': list(counts.values()), 'total': len(_feedback)}
