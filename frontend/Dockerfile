FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Les variables VITE_* sont injectées au build, pas au runtime (particularité Vite).
ARG VITE_API_URL
ARG VITE_PROJECT_ID=demo
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_PROJECT_ID=$VITE_PROJECT_ID

RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
