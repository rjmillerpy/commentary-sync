# The browser side of `make e2e`: Playwright's own image, which carries the
# browser builds this Playwright version drives. The tests run on a network
# with no internet, so everything is installed here, at build time.
#
# Built from the repository root (compose.e2e.yaml), because the sync test
# computes features with the phone's own code in client/src;
# e2e/Dockerfile.dockerignore keeps everything else out.
FROM mcr.microsoft.com/playwright:v1.63.0-noble

WORKDIR /e2e
COPY e2e/package.json e2e/package-lock.json ./
# --ignore-scripts: no package runs code at install. The browsers are in the image.
RUN npm ci --ignore-scripts
COPY e2e/ .
COPY client/src /client/src

# Chromium writes a profile under HOME; /tmp is writable for whichever user
# `make e2e` runs as (the host's, so results/ stays yours).
ENV HOME=/tmp
CMD ["npx", "playwright", "test"]
