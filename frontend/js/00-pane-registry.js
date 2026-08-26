// Agentic OS — pane renderer registry
// Registry is loaded before the core navigation module. Renderer functions are
// resolved lazily at navigation time so feature modules may load afterward.
'use strict';

window.MASTER_PANE_REGISTRY = {
  'chat':           () => {},
  'studio':         () => typeof window.initStudio === 'function' && window.initStudio(),
  // MODULE MERGE: 'builder' (Code Editor) retired and folded into 'studio'
  // (Code Studio) — nav('builder') now redirects to nav('studio') in
  // 01-app-core.js, so this registry never needs to resolve it directly.
  'templates':      () => typeof window.renderTemplates === 'function' && window.renderTemplates(),
  'composer':       () => typeof window.renderComposer === 'function' && window.renderComposer(),
  'kanban':         () => typeof window.renderKanban === 'function' && window.renderKanban(),
  'swarm':          () => typeof window.renderSwarm === 'function' && window.renderSwarm(),
  'galaxy':         () => typeof window.initGalaxy === 'function' && window.initGalaxy(),
  'hierarchy':      () => typeof window.renderHierarchy === 'function' && window.renderHierarchy(),
  'icm':            () => typeof window.renderWorkspacesIcmPane === 'function' && window.renderWorkspacesIcmPane(),
  'inbox':          () => typeof window.renderInboxPane === 'function' && window.renderInboxPane(),
  'settings':       () => typeof window.loadSettings === 'function' && window.loadSettings(),
  'dashboard':      () => typeof window.renderDashboard === 'function' && window.renderDashboard(),
  'skills':         () => typeof window.renderSkills === 'function' && window.renderSkills(),
  'deploy':         () => typeof window.renderDeploy === 'function' && window.renderDeploy(),
  'pipeline':       () => typeof window.renderPipeline === 'function' && window.renderPipeline(),
  'obsidian':       () => typeof window.renderObsidian === 'function' && window.renderObsidian(),
  'system':         () => typeof window.renderSystem === 'function' && window.renderSystem(),
  'workspaces':     () => typeof window.renderWorkspaces === 'function' && window.renderWorkspaces(),
  // Connect Hub supersedes the raw MCP tool list: one surface over tools,
  // connectors and gateway servers. Falls back to renderMCP if the hub script
  // failed to load.
  'mcp':            () => typeof window.renderConnectHub === 'function'
                            ? window.renderConnectHub()
                            : (typeof window.renderMCP === 'function' && window.renderMCP()),
  'loops':          () => typeof window.renderLoops === 'function' && window.renderLoops(),
  'github':         () => typeof window.renderGitHub === 'function' && window.renderGitHub(),
  'dbstudio':       () => typeof window.renderDBStudio === 'function' && window.renderDBStudio(),
  // Plugin Hub supersedes the old two-system split (renderPlugins over
  // /api/plugins + renderMarketplace over /api/marketplace). Falls back to the
  // legacy renderer if the hub script failed to load.
  'plugins':        () => typeof window.renderPluginHub === 'function'
                            ? window.renderPluginHub()
                            : (typeof window.renderPlugins === 'function' && window.renderPlugins()),
  'control':        () => typeof window.renderControlTower === 'function' && window.renderControlTower(),
  'webhooks':       () => typeof window.renderWebhooks === 'function' && window.renderWebhooks(),
  'testgen':        () => typeof window.renderTestGen === 'function' && window.renderTestGen(),
  'terminal':       () => typeof window.renderTerminal === 'function' && window.renderTerminal(),
  'secrets':        () => typeof window.renderSecretsVault === 'function' && window.renderSecretsVault(),
  'integrations':   () => typeof window.renderIntegrations === 'function' && window.renderIntegrations(),
  'imagegen':       () => typeof window.renderImageGen === 'function' && window.renderImageGen(),
  'prompts':        () => typeof window.renderPrompts === 'function' && window.renderPrompts(),
  'codesearch':     () => typeof window.renderCodeSearch === 'function' && window.renderCodeSearch(),
  'workflow':       () => typeof window.renderWorkflow === 'function' && window.renderWorkflow(),
  'profiler':       () => typeof window.renderProfiler === 'function' && window.renderProfiler(),
  'pluginsdk':      () => typeof window.renderPluginSDK === 'function' && window.renderPluginSDK(),
  'multitab':       () => typeof window.renderMultitab === 'function' && window.renderMultitab(),
  'specs':          () => typeof window.renderSpecs === 'function' && window.renderSpecs(),
  'hooks':          () => typeof window.renderHooks === 'function' && window.renderHooks(),
  'codeindex':      () => typeof window.renderCodeIndex === 'function' && window.renderCodeIndex(),
  'arena':          () => typeof window.renderArena === 'function' && window.renderArena(),
  'steering':       () => {}, // MODULE MERGE: folded into 'hierarchy' as a tab (window.nav() redirects 'steering' -> 'hierarchy' before this registry is ever consulted); kept as a harmless no-op entry rather than removing the key outright, in case any stale external deep-link still resolves the pane id directly.
  'bugbot':         () => typeof window.renderBugBot === 'function' && window.renderBugBot(),
  'health':         () => typeof window.renderHealth === 'function' && window.renderHealth(),
  'gitai':          () => typeof window.renderGitAI === 'function' && window.renderGitAI(),
  'ambient':        () => typeof window.renderAmbient === 'function' && window.renderAmbient(),
  'fusion':         () => typeof window.renderFusion === 'function' && window.renderFusion(),
  'hitl':           () => typeof window.renderHITL === 'function' && window.renderHITL(),
  'browser':        () => typeof window.renderBrowserAgent === 'function' && window.renderBrowserAgent(),
  'websearch':      () => typeof window.renderWebSearch === 'function' && window.renderWebSearch(),
  'leaderboard':    () => typeof window.renderLeaderboard === 'function' && window.renderLeaderboard(),
  'audit-log':      () => typeof window.renderAuditLog === 'function' && window.renderAuditLog(),
  'agent-identity': () => typeof window.renderAgentIdentity === 'function' && window.renderAgentIdentity(),
  'supervisor':     () => typeof window.renderSupervisor === 'function' && window.renderSupervisor(),
  'goals':          () => typeof window.renderGoals === 'function' && window.renderGoals(),
  'mcp-gateway':    () => typeof window.renderMCPGateway === 'function' && window.renderMCPGateway(),
  'connectors':     () => typeof window.renderConnectors === 'function' && window.renderConnectors(),
  'a2a':            () => typeof window.renderA2A === 'function' && window.renderA2A(),
  'agent-monitor':  () => typeof window.renderAgentMonitor === 'function' && window.renderAgentMonitor(),
  'finops':         () => typeof window.renderFinOps === 'function' && window.renderFinOps(),
  'eval-framework': () => typeof window.renderEvalFramework === 'function' && window.renderEvalFramework(),
  'docs':           () => typeof window.renderDocs === 'function' && window.renderDocs(),
  'evals':          () => typeof window.renderEvals === 'function' && window.renderEvals(),
  'observability':  () => typeof window.renderObservability === 'function' && window.renderObservability(),
  'knowledge-graph':() => typeof window.renderKnowledgeGraph === 'function' && window.renderKnowledgeGraph(),
  'rag':            () => typeof window.renderRAG === 'function' && window.renderRAG(),
  'replay':         () => typeof window.renderReplay === 'function' && window.renderReplay(),
  'collabedit':     () => typeof window.renderCollabEdit === 'function' && window.renderCollabEdit(),
  'marketplace':    () => typeof window.renderMarketplace === 'function' && window.renderMarketplace(),
  'pqc':            () => typeof window.renderPQCVault === 'function' && window.renderPQCVault(),
  'finetune':       () => typeof window.renderFinetuneWorkstation === 'function' && window.renderFinetuneWorkstation(),
};
