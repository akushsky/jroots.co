FROM node:20-alpine as builder

WORKDIR /app
COPY ./frontend /app
RUN npm install && npm run build

# Serve with nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY ./frontend/nginx.conf /etc/nginx/conf.d/default.conf