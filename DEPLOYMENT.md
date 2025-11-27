# DEPLOYMENT to Render (manual steps)

Render automatic deploy requires a Git repo pushed to GitHub/GitLab. Below are instructions to deploy this service to Render.

1. Initialize the git repo (see GIT_INIT.sh for commands)
2. Push to GitHub
3. On Render:
   - Create a new Web Service
   - Connect your GitHub repo
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Set health check to `/docs` or `/health` (if implemented)
4. Environment variables:
   - No required env vars for the demo, but set `HOSPITAL_API_BASE` if the production API differs.

If you'd like, I can prepare a render.yaml or a Docker deployment config; note I cannot push to Render for you but will provide all files required.
