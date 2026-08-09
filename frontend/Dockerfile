FROM node:22-alpine AS builder
ARG CDN_BASE=/
ARG VITE_REGISTRATION_ENABLED=true
ENV CDN_BASE=${CDN_BASE}
ENV VITE_REGISTRATION_ENABLED=${VITE_REGISTRATION_ENABLED}

WORKDIR /app
COPY ./frontend /app
RUN npm ci && npm run build

# Serve with nginx
FROM nginx:alpine
ARG NGINX_CONF=nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY ./frontend/${NGINX_CONF} /etc/nginx/conf.d/default.conf