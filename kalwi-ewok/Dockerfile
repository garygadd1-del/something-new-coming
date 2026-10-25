# syntax=docker/dockerfile:1

# Kalwi Ewok runtime image.
# One short-lived seat: non-root, no listener, no secrets, no GPU toolkit.
# There is no compile step, so this stays a single runtime stage.
# The entrypoint needs a shell for the baked stub hooks, so the base is Alpine
# rather than a shell-less image.

FROM alpine:3.20

LABEL org.opencontainers.image.title="kalwi-ewok" \
      org.opencontainers.image.description="Short-lived isolated AGIOS hive agent scaffold. No secrets, no GPU, no prod deploy." \
      org.opencontainers.image.source="https://github.com/garygadd1-del/something-new-coming"

RUN addgroup -S -g 1001 kalwi \
    && adduser -S -D -H -u 1001 -G kalwi kalwi

WORKDIR /opt/kalwi

COPY --link --chown=1001:1001 skills/ /opt/kalwi/skills/
COPY --link --chown=1001:1001 agent/entrypoint.sh /opt/kalwi/entrypoint.sh

RUN chmod 0755 /opt/kalwi/entrypoint.sh \
    && chmod -R a-w /opt/kalwi

USER 1001:1001

# Literals only. None of these are credentials.
ENV HOME=/tmp \
    KALWI_GPU=off \
    KALWI_TASK=stub \
    KALWI_PROD_DEPLOY=0 \
    KALWI_MONEY_SENDS=0 \
    KALWI_SECRETS=none

# The seat does not listen.
ENTRYPOINT ["/opt/kalwi/entrypoint.sh"]
