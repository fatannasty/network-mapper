FROM node:20-alpine

RUN apk add --no-cache openssh-client sshpass

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --production

COPY server.js scanner.js ssh-scanner.js ./
COPY app.js style.css index.html ./
COPY icons/ ./icons/

EXPOSE 7777

CMD ["node", "server.js"]
