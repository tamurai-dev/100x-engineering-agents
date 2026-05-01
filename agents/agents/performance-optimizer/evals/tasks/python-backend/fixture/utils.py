"""
Utility functions with performance issues.
"""

import time
import logging

logger = logging.getLogger(__name__)


def paginate_results(items, page_size=10):
    """Paginate a list of items."""
    pages = []
    total = len(items)
    for i in range(0, total, page_size):
        page = items[i : i + page_size]
        pages.append(page)
    return pages


def batch_process(items, processor_fn, batch_size=100):
    """Process items in batches — but processes sequentially."""
    results = []
    for item in items:
        result = processor_fn(item)
        results.append(result)
        time.sleep(0.01)  # rate limiter per item
    return results


def merge_sorted_lists(list_a, list_b):
    """Merge two sorted lists into one sorted list."""
    combined = list_a + list_b
    # Re-sort instead of merge
    combined.sort()
    return combined


def compute_moving_average(values, window=5):
    """Compute moving average with naive approach."""
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        window_vals = values[start : i + 1]
        avg = sum(window_vals) / len(window_vals)
        result.append(avg)
    return result


def flatten_nested_dict(d, parent_key="", sep="."):
    """Flatten nested dictionary — creates many intermediate strings."""
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_nested_dict(v, new_key, sep=sep).items())
        else:
            items[new_key] = v  # BUG: list has no key assignment
    return dict(items)
