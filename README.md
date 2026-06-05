# Claude Code + OpenCode Local Delegation Skill

A standardized global skill for Claude Code that delegates token-heavy implementation, repetitive boilerplate, and massive test generation tasks to a local LLM running via OpenCode + LM Studio.

## 🛠️ Setup Instructions
1. Clone this repository directly into your global Claude skills folder:
   ```bash
   git clone <YOUR_GITHUB_REPO_URL> ~/.claude/skills/opencode-delegate
   ```
2. Set up **LM Studio** on your local machine with an OpenAI-compatible local server running on port `1234`.
3. Update your `~/.config/opencode/opencode.json` configuration file to point to your local provider:
   ```json
   {
     "provider": {
       "lmstudio": {
         "name": "LM Studio (Local)",
         "npm": "@ai-sdk/openai-compatible",
         "options": { "baseURL": "http://127.0.0", "apiKey": "lm-studio" },
         "models": { "your-local-model": { "name": "your-local-model" } }
       }
     },
     "model": "lmstudio/your-local-model"
   }
   ```

## 🚀 Usage
Inside any interactive `claude` session, type:
> "Plan the architecture for a new feature, then write the spec to `.local_task.md` and use the opencode delegate skill to implement it."
