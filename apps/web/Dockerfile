FROM node:22.12.0-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN chown -R node:node /app
USER node

EXPOSE 3000
# Vite dev server with hot reload; /api is proxied to API_PROXY_TARGET.
CMD ["npm", "run", "dev"]
