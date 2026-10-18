from types import MethodType


def install(model, maximum_spans=64):
    import torch
    from gliner.modeling.base import UniEncoderTokenRelexModel

    maximum_spans = int(maximum_spans)
    if maximum_spans < 1:
        raise ValueError("Maximum Relex spans must be at least one")
    inner = model.model
    if not isinstance(inner, UniEncoderTokenRelexModel):
        return model
    inner._argus_max_spans = maximum_spans
    if getattr(inner, "_argus_bounded_spans", False):
        return model
    original = inner.represent_spans

    def pack(scores, ranked_spans, candidate_count, maximum):
        width = max(1, max((min(len(ranked), maximum) for ranked in ranked_spans), default=0))
        indices = torch.zeros((scores.size(0), width, 2), dtype=torch.long, device=scores.device)
        mask = torch.zeros((scores.size(0), width), dtype=torch.bool, device=scores.device)
        metrics = []
        for batch_index, (candidates, ranked) in enumerate(zip(candidate_count, ranked_spans, strict=True)):
            selected = ranked[:maximum]
            if selected:
                indices[batch_index, :len(selected)] = torch.tensor([(start, end) for _, start, end in selected], dtype=torch.long, device=scores.device)
                mask[batch_index, :len(selected)] = True
            metrics.append({"candidates": int(candidates), "retained": len(selected), "truncated": max(0, int(candidates) - len(selected)), "limit": maximum, "rankScore": "minimum of maximum start/end token probabilities; beam priority only, not truth confidence"})
        return indices, mask, metrics

    def select_predicted_spans(scores, threshold, maximum):
        batch_size, token_count, class_count, _ = scores.shape
        probabilities = torch.sigmoid(scores)
        starts_mask = probabilities[..., 0] > threshold
        ends_mask = probabilities[..., 1] > threshold
        inside_mask = probabilities[..., 2] > threshold
        inside_prefix = torch.nn.functional.pad(inside_mask.long().cumsum(dim=1), (0, 0, 1, 0))
        ranked_batches = []
        candidate_counts = []
        for batch_index in range(batch_size):
            seen = torch.zeros((token_count, token_count), dtype=torch.bool, device=scores.device)
            ranked_candidates = []
            for class_index in range(class_count):
                starts = starts_mask[batch_index, :, class_index].nonzero(as_tuple=False).flatten()
                ends = ends_mask[batch_index, :, class_index].nonzero(as_tuple=False).flatten()
                if starts.numel() == 0 or ends.numel() == 0:
                    continue
                end_prefix = inside_prefix[batch_index, :, class_index]
                end_probabilities = probabilities[batch_index, :, class_index, 1]
                for start_group in starts.split(32):
                    start_grid = start_group[:, None]
                    end_grid = ends[None, :]
                    lengths = end_grid - start_grid + 1
                    inside_counts = end_prefix[end_grid + 1] - end_prefix[start_grid]
                    valid = (lengths > 0) & (inside_counts == lengths)
                    prior = seen[start_grid, end_grid]
                    seen[start_grid, end_grid] = prior | valid
                    if not valid.any():
                        continue
                    scores_by_start = probabilities[batch_index, start_group, class_index, 0]
                    pair_rank = torch.minimum(scores_by_start[:, None], end_probabilities[ends][None, :]).masked_fill(~valid, float("-inf"))
                    take = min(maximum, pair_rank.numel())
                    values, flat_indices = torch.topk(pair_rank.reshape(-1), take)
                    valid_top = torch.isfinite(values)
                    if not valid_top.any():
                        continue
                    values = values[valid_top].detach().cpu().tolist()
                    flat_indices = flat_indices[valid_top].detach().cpu().tolist()
                    for value, flat_index in zip(values, flat_indices, strict=True):
                        start_index, end_index = divmod(flat_index, ends.numel())
                        ranked_candidates.append((float(value), int(start_group[start_index]), int(ends[end_index])))
            unique = {}
            for score, start, end in ranked_candidates:
                key = (start, end)
                if key not in unique or score > unique[key]:
                    unique[key] = score
            ranked = sorted(((score, start, end) for (start, end), score in unique.items()), key=lambda value: (-value[0], value[1], value[2]))
            ranked_batches.append(ranked)
            candidate_counts.append(int(seen.sum().item()))
        return pack(scores, ranked_batches, candidate_counts, maximum)

    def select_supplied_spans(scores, span_idx, span_mask, maximum):
        probabilities = torch.sigmoid(scores)
        ranked_batches = []
        candidate_counts = []
        for batch_index, (indices, valid) in enumerate(zip(span_idx, span_mask, strict=True)):
            spans = torch.unique(indices[valid.bool()], dim=0)
            candidates = []
            for start, end in spans.detach().cpu().tolist():
                if start < 0 or end < start or end >= scores.size(1):
                    continue
                start_scores = probabilities[batch_index, start, :, 0]
                end_scores = probabilities[batch_index, end, :, 1]
                score = torch.minimum(start_scores, end_scores).max().item()
                candidates.append((float(score), int(start), int(end)))
            candidates.sort(key=lambda value: (-value[0], value[1], value[2]))
            ranked_batches.append(candidates)
            candidate_counts.append(len(candidates))
        return pack(scores, ranked_batches, candidate_counts, maximum)

    def represent(self, words_embeddings, words_mask, prompts_embeddings, span_idx=None, span_mask=None, labels=None, threshold=0.5, return_embeddings=False):
        if self.training or labels is not None:
            self._argus_span_metrics = []
            return original(words_embeddings, words_mask, prompts_embeddings, span_idx, span_mask, labels, threshold, return_embeddings)
        scores = self.scorer(words_embeddings, prompts_embeddings)
        maximum = int(getattr(self, "_argus_max_spans", 64))
        if span_idx is None:
            indices, mask, metrics = select_predicted_spans(scores, threshold, maximum)
        else:
            if span_mask is None:
                span_mask = torch.ones(span_idx.shape[:2], dtype=torch.bool, device=span_idx.device)
            indices, mask, metrics = select_supplied_spans(scores, span_idx, span_mask, maximum)
        self._argus_span_metrics = metrics
        result = (scores, self.span_rep_layer(words_embeddings, indices), mask, indices)
        return (*result, None) if return_embeddings else result

    inner.represent_spans = MethodType(represent, inner)
    projection = getattr(inner, "pair_rep_layer", None)
    if projection is not None:
        project = projection.forward

        def forward(self, value):
            if self.training or value.size(-2) <= 256:
                return project(value)
            return torch.cat([project(part) for part in value.split(256, dim=-2)], dim=-2)

        projection.forward = MethodType(forward, projection)
    inner._argus_bounded_spans = True
    inner._argus_span_metrics = []
    return model
