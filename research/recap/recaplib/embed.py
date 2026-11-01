"""Torch-free sentence embeddings: all-MiniLM-L6-v2 forward pass in numpy.

Weights: sentence-transformers/all-MiniLM-L6-v2 (safetensors, sha256 53aa5117...).
Mean pooling + L2 norm, identical to the sentence-transformers recipe.
~1-2 ms/sentence on CPU in batches; good enough for scenes/beats/cues.
"""
from __future__ import annotations
import json, os
import numpy as np
from . import MODELS

_M = None


def _gelu(x):
    from scipy.special import erf
    return (0.5 * x * (1.0 + erf(x * float(1 / np.sqrt(2.0))))).astype(np.float32)


def _ln(x, g, b, eps=1e-12):
    mu = x.mean(-1, keepdims=True)
    var = ((x - mu) ** 2).mean(-1, keepdims=True)
    return ((x - mu) / np.sqrt(var + eps) * g + b).astype(np.float32)


class MiniLM:
    def __init__(self, path=os.path.join(MODELS, "minilm")):
        from safetensors.numpy import load_file
        from tokenizers import Tokenizer
        self.w = {k.replace("bert.", ""): v.astype(np.float32) for k, v in load_file(os.path.join(path, "model.safetensors")).items()}
        cfg = json.load(open(os.path.join(path, "config.json")))
        self.L, self.H = cfg["num_hidden_layers"], cfg["num_attention_heads"]
        self.tok = Tokenizer.from_file(os.path.join(path, "tokenizer.json"))
        self.tok.enable_truncation(256)
        self.tok.enable_padding(pad_id=0, pad_token="[PAD]")

    def _forward(self, ids, mask):
        w = self.w
        B, T = ids.shape
        x = w["embeddings.word_embeddings.weight"][ids] + w["embeddings.position_embeddings.weight"][np.arange(T)][None] \
            + w["embeddings.token_type_embeddings.weight"][0][None, None]
        x = _ln(x, w["embeddings.LayerNorm.weight"], w["embeddings.LayerNorm.bias"])
        D = x.shape[-1]; hd = D // self.H
        bias = ((1.0 - mask[:, None, None, :]) * -1e9).astype(np.float32)
        for i in range(self.L):
            p = f"encoder.layer.{i}."
            def lin(h, n):  # 2-D BLAS path (3-D matmul is ~70x slower in some numpy builds)
                sh = h.shape
                return (h.reshape(-1, sh[-1]) @ w[p + n + ".weight"].T + w[p + n + ".bias"]).reshape(*sh[:-1], -1)
            q = lin(x, "attention.self.query").reshape(B, T, self.H, hd).transpose(0, 2, 1, 3)
            k = lin(x, "attention.self.key").reshape(B, T, self.H, hd).transpose(0, 2, 1, 3)
            v = lin(x, "attention.self.value").reshape(B, T, self.H, hd).transpose(0, 2, 1, 3)
            a = np.einsum("bhtd,bhsd->bhts", q, k, optimize=True) * float(1.0 / np.sqrt(hd)) + bias
            a = np.exp(a - a.max(-1, keepdims=True)); a /= a.sum(-1, keepdims=True)
            o = np.einsum("bhts,bhsd->bhtd", a, v, optimize=True).transpose(0, 2, 1, 3).reshape(B, T, D)
            x = _ln(x + lin(o, "attention.output.dense"), w[p + "attention.output.LayerNorm.weight"], w[p + "attention.output.LayerNorm.bias"])
            h = _gelu(lin(x, "intermediate.dense"))
            x = _ln(x + lin(h, "output.dense"), w[p + "output.LayerNorm.weight"], w[p + "output.LayerNorm.bias"])
        m = mask[..., None]
        e = (x * m).sum(1) / np.maximum(m.sum(1), 1e-9)
        return e / np.linalg.norm(e, axis=1, keepdims=True)

    def encode(self, texts, batch=32):
        """Length-sorted batching (minimal padding), results returned in input order."""
        texts = [t or "" for t in texts]
        if not texts:
            return np.zeros((0, 384), np.float32)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = np.zeros((len(texts), 384), np.float32)
        for i in range(0, len(order), batch):
            idx = order[i:i + batch]
            enc = self.tok.encode_batch([texts[j] for j in idx])
            ids = np.array([e.ids for e in enc]); mask = np.array([e.attention_mask for e in enc], dtype=np.float32)
            out[idx] = self._forward(ids, mask)
        return out


def model():
    global _M
    if _M is None:
        _M = MiniLM()
    return _M


def encode(texts, batch=32):
    return model().encode(list(texts), batch)
