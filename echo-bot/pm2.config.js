module.exports = {
  apps: [{
    name: 'echo-bot',
    script: 'bot.py',
    interpreter: 'python',
    watch: false,
    autorestart: true,
    max_restarts: 10,
    restart_delay: 3000,
    env: {
      PYTHONUNBUFFERED: '1',
    },
  }],
}
