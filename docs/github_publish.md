# Publish To GitHub

## 1. Initialize repository

git init
git add .
git commit -m "feat: initial danxi daily skill"

## 2. Create remote repository

Recommended repo name:
danxi-daily-skill

Remote URL:
https://github.com/0patsick0/danxi-daily-skill.git

## 3. Push

git branch -M main
git remote add origin https://github.com/0patsick0/danxi-daily-skill.git
git push -u origin main

## 4. Share install URL

skill install https://github.com/0patsick0/danxi-daily-skill

## 5. First-run config

Set environment variables before first use:
- DANXI_API_TOKEN (optional for read, required on some deployments)
- OPENAI_API_KEY or ANTHROPIC_API_KEY (optional)
- DANXI_POST_TOKEN (required for --post)
