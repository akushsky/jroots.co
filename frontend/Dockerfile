FROM node:22-alpine AS builder
ARG CDN_BASE=/
ENV CDN_BASE=${CDN_BASE}

WORKDIR /app
COPY ./frontend /app
RUN npm ci && npm run build

# Serve with nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY ./frontend/nginx.conf /etc/nginx/conf.d/default.conf