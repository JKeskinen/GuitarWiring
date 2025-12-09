# Deployment Guide: Humbucker Solver on Render.com

## Quick Start

### 1. **Connect GitHub Repository**
   - Go to [render.com](https://render.com)
   - Click **"New +"** → **"Web Service"**
   - Select **"Deploy an existing repo from GitHub"**
   - Choose this repository: `GuitarWiring`
   - Click **"Connect"**

### 2. **Configure the Service**
   - **Name:** `humbucker-solver` (or your preference)
   - **Environment:** Python 3.11
   - **Build Command:** `pip install -r app/requirements.txt`
   - **Start Command:** `streamlit run app/main.py --server.port=$PORT --server.address=0.0.0.0`
   - **Plan:** Free (or Standard for better performance)

### 3. **Environment Variables (Optional)**
   If you want to use a cloud-hosted Ollama instance for AI streaming:
   - Add **OLLAMA_URL**: `https://your-ollama-instance.com`
   - Add **OLLAMA_MODEL**: `mistral:7b` (default)

   Without these, the app will use the built-in **static FAQ mode** (soldering, grounding, hum-cancelling tips).

### 4. **Deploy**
   - Click **"Create Web Service"**
   - Render will automatically deploy when you push to GitHub

---

## Features on Render

✅ **Fully Functional Without Ollama**
- Static FAQ mode (soldering, grounding, hum-cancelling, phase checking, coil splitting)
- Easter eggs still work (type "42", "hello there", etc. in the AI sidebar)
- All wiring calculations and analysis work normally

✅ **Optional: Full AI Streaming**
- Set `OLLAMA_URL` to a cloud Ollama instance for full AI responses
- Example cloud Ollama hosts:
  - [Replicate](https://replicate.com) - `https://api.replicate.com/v1`
  - [Together AI](https://www.together.ai) - Self-hosted option
  - Your own Ollama server with public URL

---

## Troubleshooting

### Build fails: "ModuleNotFoundError"
- Check that `app/requirements.txt` exists and is correct
- Render should auto-detect it from the build command

### App crashes on startup
- Check logs in Render dashboard: **"Logs"** tab
- Common issue: Streamlit config not found
  - Solution: `.streamlit/config.toml` is included in repo

### Streamlit says "port already in use"
- This is handled by the start command: `--server.port=$PORT`
- Render sets `$PORT` automatically

### AI Assistant says "unavailable"
- This is normal without `OLLAMA_URL` set
- App falls back to static FAQ mode gracefully
- To enable full AI: set `OLLAMA_URL` environment variable

---

## Performance Tips

**Free Tier:**
- Runs on shared resources
- OK for light use and demos
- May spin down after 15 minutes of inactivity

**Standard Tier:**
- Dedicated resources
- Always-on
- Better for production use

---

## Git Workflow

The app auto-deploys when you push to GitHub's `main` branch:

```powershell
git add -A
git commit -m "Your changes"
git push origin main
```

Render will:
1. Detect the push
2. Run build command
3. Deploy automatically
4. You'll see status in Render dashboard

---

## URL
Once deployed, your app will be available at:
`https://humbucker-solver.onrender.com/` (or your custom domain)

---

## Questions?
- Check Render logs for errors
- Verify `render.yaml` and `.streamlit/config.toml` are in repo root
- Make sure `app/requirements.txt` is up-to-date
