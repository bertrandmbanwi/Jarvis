# JARVIS web UI. JARVIS_API_HOST is read at build time (Next.js rewrites).
FROM node:24-slim AS build
WORKDIR /ui
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG JARVIS_API_HOST=api
ENV JARVIS_API_HOST=${JARVIS_API_HOST}
RUN npm run build

FROM node:24-slim
WORKDIR /ui
ENV NODE_ENV=production JARVIS_API_HOST=api
COPY --from=build /ui ./
USER node
EXPOSE 3000
CMD ["npm", "start"]
