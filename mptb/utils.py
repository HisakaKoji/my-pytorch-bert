# Author Toshihiko Aoki
#
# Copyright 2018 The Google AI Language Team Authors(truncate_seq_pair).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Utility Functions"""

import os
import time
import random
import logging
import numpy as np
import torch
from .preprocessing import *


class Timer(object):
    def __init__(self, verbose=False):
        self.verbose = verbose

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.end = time.time()
        self.secs = self.end - self.start
        self.msecs = self.secs * 1000  # millisecs
        if self.verbose:
            print('elapsed time: %f ms' % self.msecs)


def to_bert_ids(
    max_pos, tokenizer, sentence_a, sentence_b,
    cls_token='[CLS]', sep_token='[SEP]', pad_token='[PAD]'
):
    tokens_a = tokenizer.tokenize(sentence_a)
    tokens_b = tokenizer.tokenize(sentence_b) if sentence_b is not None else []

    # max_pos truncate
    max_seq_len = max_pos - 3 if tokens_b else max_pos - 2
    truncate_seq_pair(tokens_a, tokens_b, max_seq_len)

    # Add Special Tokens
    tokens_a = [cls_token] + tokens_a + [sep_token]
    tokens_b = tokens_b + [sep_token] if len(tokens_b) > 0 else []

    # input ids build
    input_ids = tokens_a + tokens_b
    segment_ids = [0] * len(tokens_a) + [1] * len(tokens_b)
    input_mask = [1] * len(input_ids)

    # padding
    num_zero_pad = max_pos - len(input_ids)
    input_ids.extend([pad_token] * num_zero_pad)
    segment_ids.extend([0] * num_zero_pad)
    input_mask.extend([0] * num_zero_pad)

    # tokens indexing
    input_ids = tokenizer.convert_tokens_to_ids(input_ids)

    return [input_ids, segment_ids, input_mask]


def get_tokenizer(
    preprocessor=None,
    vocab_path=None,
    sp_model_path=None,
    name='google'
):
    if preprocessor is None:
        preprocessor = default_preprocessor()

    if sp_model_path is not None and vocab_path is not None:
        from .tokenization_sentencepiece import FullTokenizer
        return FullTokenizer(sp_model_path, vocab_path, preprocessor=preprocessor)
    elif vocab_path is not None:
        name = name.lower()
        if name == 'mecab':
            from .tokenization_mecab import FullTokenizer
            return FullTokenizer(vocab_path, preprocessor=preprocessor)
        elif name == 'juman':
            from .tokenization_juman import FullTokenizer
            return FullTokenizer(vocab_path, preprocessor=preprocessor)
        # google bert tokenizer use
        else:
            from .tokenization import FullTokenizer
            return FullTokenizer(vocab_path, preprocessor=preprocessor)


def default_preprocessor():
    return Pipeline([
        ToUnicode(),
        Normalize(),
        LowerCase(),
        ReplaceNumber(),
        ReplaceURI(),
    ])


def japanese_stopwords():
    slothlib_stopwords = []
    with open('dict/slothlib_include_Japanese.txt', "r", encoding='UTF-8') as reader:
        for line in reader:
            line = line.strip()
            if line == '':
                continue
            slothlib_stopwords.append(line)
    return slothlib_stopwords


def make_balanced_classes_weights(per_label_records_num):
    all_records_num = sum(per_label_records_num)
    label_num = len(per_label_records_num)
    classes_weights = [0] * label_num
    for i in range(label_num):
        classes_weights[i] = all_records_num / (label_num * per_label_records_num[i])
    return classes_weights


def get_one_hot(x, depth):
    """get One-Hot tensor."""
    converted = x.view(-1, 1)
    one_hot = torch.zeros(converted.size()[0], depth, device=x.device).scatter_(1, converted, 1)
    one_hot = one_hot.view(*(tuple(x.shape) + (-1,)))
    return one_hot


def get_device():
    """get pytorch device"""
    return 'cuda' if torch.cuda.is_available() else 'cpu'


def set_seeds(seed):
    """Set components randam seed"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# Copyright 2018 The Google AI Language Team Authors.
def truncate_seq_pair(tokens_a, tokens_b, max_length):
    """Truncates a sequence pair in place to the maximum length."""

    # This is a simple heuristic which will always truncate the longer sequence
    # one token at a time. This makes more sense than truncating an equal percent
    # of tokens from each, since if one sequence is very short then each token
    # that's truncated likely contains more information than a longer sequence.
    while True:
        total_length = len(tokens_a) + len(tokens_b)
        if total_length <= max_length:
            break
        if len(tokens_a) > len(tokens_b):
            tokens_a.pop()
        else:
            tokens_b.pop()


def get_logger(name, log_path=None, is_console=False, level=None):
    """Python Logger"""
    logger = logging.getLogger(name)
    logger.propagate = False
    log_format = logging.Formatter(
        '%(asctime)s:%(levelname)s:[%(filename)s:%(lineno)s]:%(message)s')
    if level is None:
        level = logging.DEBUG
    if is_console:
        handler = logging.StreamHandler()
        handler.setFormatter(log_format)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        if log_path is None:
            return logger

    assert log_path is not None, 'require log_path'

    if not os.path.isfile(log_path):
        import warnings
        if not os.path.isdir(log_path):
            dir_path = os.path.dirname(log_path)
            if dir_path == '':
                dir_path = log_path
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                warnings.warn("logfile dir makedir -p : " + dir_path)
        if os.path.exists(log_path) and os.path.isdir(log_path):
            if log_path[-1] is not '/':
                log_path = log_path + "/"
            log_path = log_path + name + ".log"
        open(log_path, 'a').close()

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
    logger.setLevel(level)
    return logger


def load(model, filename, device='cpu', optimizer=None):
    """Loading pytorch model and optimizer(Option)."""
    
    loading_dict = torch.load(filename, map_location=device)
    if 'model' in loading_dict:
        model.load_state_dict(loading_dict['model'])
    else:
        model.load_state_dict(loading_dict)
    if optimizer is not None and 'optimizer' in loading_dict:
        optimizer.load_state_dict(loading_dict['optimizer'])


def save(model, filename, optimizer=None):
    """Saving pytorch model and optimizer(Option)."""
    
    if optimizer is not None:
        saving_dict = {
            'model': model.state_dict(),
            'optimizer': optimizer.state_dict()
        }
    else:
        saving_dict = model.state_dict()
    torch.save(saving_dict, filename)
