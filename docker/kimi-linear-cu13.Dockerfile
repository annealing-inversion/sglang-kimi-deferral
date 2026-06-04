# Runtime image for validating Kimi-Linear on Blackwell GPUs without CPU offload.
# Keep model weights out of the image; mount them or let SGLang download them.
ARG SGLANG_BASE_IMAGE=lmsysorg/sglang:latest-cu130-runtime
FROM ${SGLANG_BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/workspace/.cache/huggingface \
    TRANSFORMERS_CACHE=/workspace/.cache/huggingface \
    HF_HUB_ENABLE_HF_TRANSFER=1

# distro is required by the OpenAI package import path in some SGLang images.
# hf_transfer speeds up large model downloads when the network allows it.
RUN python3 -m pip install --no-cache-dir -U pip && \
    python3 -m pip install --no-cache-dir distro hf_transfer

WORKDIR /sgl-workspace/sglang

COPY docker/kimi-linear-env-check.sh /usr/local/bin/kimi-linear-env-check
RUN chmod +x /usr/local/bin/kimi-linear-env-check

CMD ["/bin/bash"]
