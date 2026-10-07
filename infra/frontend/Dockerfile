FROM node:22-alpine AS build
WORKDIR /app
RUN npm install --global pnpm@10.17.1
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/tsconfig.json frontend/index.html ./
COPY frontend/src ./src
COPY frontend/public ./public
RUN pnpm test && pnpm build

FROM nginx:stable-alpine
COPY infra/frontend/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
