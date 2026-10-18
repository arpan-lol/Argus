from types import MethodType


def install(model):
    import torch
    from gliner.modeling.base import UniEncoderTokenRelexModel
    from gliner.modeling.utils import extract_spans_from_tokens

    inner = model.model
    if not isinstance(inner, UniEncoderTokenRelexModel) or getattr(inner, '_argus_bounded_spans', False):
        return model
    original = inner.represent_spans

    def represent(self, words_embeddings, words_mask, prompts_embeddings, span_idx=None, span_mask=None, labels=None, threshold=0.5, return_embeddings=False):
        if self.training or labels is not None:
            return original(words_embeddings, words_mask, prompts_embeddings, span_idx, span_mask, labels, threshold, return_embeddings)
        scores = self.scorer(words_embeddings, prompts_embeddings)
        if span_idx is None:
            span_idx, span_mask = extract_spans_from_tokens(scores, labels, threshold)
        spans = [torch.unique(indices[valid.bool()], dim=0) for indices, valid in zip(span_idx, span_mask, strict=True)]
        maximum = max(1, max((len(values) for values in spans), default=0))
        indices = span_idx.new_zeros(len(spans), maximum, 2)
        mask = span_mask.new_zeros(len(spans), maximum)
        for index, values in enumerate(spans):
            indices[index, :len(values)] = values
            mask[index, :len(values)] = True
        result = (scores, self.span_rep_layer(words_embeddings, indices), mask, indices)
        return (*result, None) if return_embeddings else result

    inner.represent_spans = MethodType(represent, inner)
    projection = getattr(inner, 'pair_rep_layer', None)
    if projection is not None:
        project = projection.forward

        def forward(self, value):
            if self.training or value.size(-2) <= 256:
                return project(value)
            return torch.cat([project(part) for part in value.split(256, dim=-2)], dim=-2)

        projection.forward = MethodType(forward, projection)
    inner._argus_bounded_spans = True
    return model
