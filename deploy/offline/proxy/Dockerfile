# Resolved on the connected preparation host; the release records the built ID.
FROM docker.io/library/nginx:1.30.6-alpine@sha256:959ae6b898852db82e5b29b929388e59914f42be0a8f4d44c89a4c1f53b49208
COPY deploy/offline/proxy/nginx.conf /etc/nginx/nginx.conf
USER 10001:10001
EXPOSE 8443
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
