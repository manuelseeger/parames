FROM node:22-bookworm

# GitHub tooling, uv's Python build prerequisites, and Chromium runtime libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
  git curl jq ca-certificates gnupg \
  build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
  libffi-dev liblzma-dev libncursesw5-dev tk-dev uuid-dev \
  libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 \
  libgbm1 libasound2 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxdamage1 \
  libxext6 libxfixes3 libxrandr2 libxkbcommon0 libpango-1.0-0 libcairo2 libgtk-3-0 \
  fonts-liberation xdg-utils \
  && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
  && apt-get update && apt-get install -y --no-install-recommends gh \
  && rm -rf /var/lib/apt/lists/*

# Build args are supplied by Sandcastle to align bind-mounted file ownership.
ARG AGENT_UID=1000
ARG AGENT_GID=1000
RUN groupmod -o -g $AGENT_GID node \
  && usermod -o -u $AGENT_UID -g $AGENT_GID -d /home/agent -m -l agent node

USER ${AGENT_UID}:${AGENT_GID}
ENV PATH="/home/agent/.local/bin:$PATH"

# uv installs and manages the requested Python independently of Bookworm's Python.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
  && uv python install 3.13 --default \
  && npm config set prefix /home/agent/.local \
  && npm install --global @playwright/cli playwright \
  && "$(npm prefix --global)/bin/playwright" install chromium

# Keep the template's Claude Code installation and its user-local setup.
RUN curl -fsSL https://claude.ai/install.sh | bash

WORKDIR /home/agent
ENTRYPOINT ["sleep", "infinity"]
