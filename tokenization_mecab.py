# Author Toshihiko Aoki
#
# This file is based on https://github.com/google-research/bert/blob/master/tokenization.py and
# Mecab tokenizer.
#
# Copyright 2018 The Google AI Language Team Authors.
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

import six
import MeCab
from random import randint
from collections import Counter, OrderedDict
from tqdm import tqdm

CONTROL_TOKENS = ['[UNK]', '[CLS]', '[SEP]', '[MASK]']


def convert_to_unicode(text):
    """Converts `text` to Unicode (if it's not already), assuming utf-8 input."""
    if six.PY3:
        if isinstance(text, str):
            return text
        elif isinstance(text, bytes):
            return text.decode("utf-8", "ignore")
        else:
            raise ValueError("Unsupported string type: %s" % (type(text)))
    else:
        raise ValueError("Not running on Python 3")


def create_vocab(text_file_path, create_file_path, min_freq=1, limit_vocab_length=-1,
                 collect_futures=[], control_tokens=CONTROL_TOKENS):
    with open(text_file_path, "r", encoding='utf-8') as reader:
        return text_to_vocab(reader, create_file_path, min_freq=min_freq, limit_vocab_length=limit_vocab_length,
                             collect_futures=collect_futures, control_tokens=control_tokens)


def text_to_vocab(reader, create_file_path, min_freq=1, limit_vocab_length=-1,
                  collect_futures=[], control_tokens=CONTROL_TOKENS):

    mecab_tokenizer = MecabTokenizer(collect_futures=collect_futures)
    min_freq = max(min_freq, 1)
    counter = Counter()
    for _, line in enumerate(tqdm(reader)):
        sentence = convert_to_unicode(line)
        if not sentence:
            break
        tokens = mecab_tokenizer.tokenize(sentence)
        for word in tokens:
            counter[word] += 1
    sort_freq = sorted(counter.items(), key=lambda tup: tup[0])
    sort_freq.sort(key=lambda tup: tup[1], reverse=True)

    with open(create_file_path, "w", encoding='utf-8', newline='\n') as f:
        for control in control_tokens:
            del counter[control]
            f.write(control+'\t0\n')
        size = len(control_tokens)

        for word, freq in sort_freq:
            if freq < min_freq:
                continue
            f.write(word+'\t'+str(freq)+'\n')
            size += 1
            if limit_vocab_length != -1 and limit_vocab_length < size:
                break
    return size


class MecabTokenizer(object):

    def __init__(self, args='', collect_futures=[]):
        self.tagger = MeCab.Tagger(args)
        self.collect_futures = collect_futures

    def tokenize(self, text):
        tokens = []
        self.tagger.parse('')
        for chunk in self.tagger.parse(text.rstrip()).splitlines()[:-1]:  # skip EOS
            if chunk == '' or '\t' not in chunk:  # often there is not include tab
                continue
            (surface, features) = chunk.split('\t')
            if len(self.collect_futures) == 0:
                tokens.append(surface.strip())
            else:
                feature = feature.split(',')
                if feature[0] in self.collect_futures:
                    tokens.append(surface)
        return tokens


def load_vocab(vocab_file):
    """Loads a vocabulary file into a dictionary."""
    try:
        import tensorflow as tf
        with tf.gfile.GFile(vocab_file, "r") as reader:
            return token_vocab_build(reader)

    except ImportError:
        with open(vocab_file, "r", encoding='utf-8') as reader:
            return token_vocab_build(reader)


def token_vocab_build(reader):
    vocab_dict = OrderedDict()
    index = 0
    for _, token in enumerate(tqdm(reader)):
        word, _ = token.split("\t")
        word = word.strip()
        vocab_dict[word] = index
        index += 1
    return vocab_dict


def convert_by_vocab(vocab_dict, items, unk_info):
    """Converts a sequence of [tokens|ids] using the vocab."""
    output = []
    for item in items:
        if item in vocab_dict:
            output.append(vocab_dict[item])
        else:
            output.append(unk_info)
    return output


def convert_tokens_to_ids(vocab, tokens):
    """Id of <unk> is assumed as 0"""
    return convert_by_vocab(vocab, tokens, unk_info=0)


def convert_ids_to_tokens(inv_vocab, ids):
    """Token of unknown word is assumed as [UNK]"""
    return convert_by_vocab(inv_vocab, ids, unk_info='[UNK]')


class FullTokenizer(object):
    """Runs end-to-end tokenziation."""

    def __init__(self, vocab_file, control_tokens=CONTROL_TOKENS):
        self.tokenizer = MecabTokenizer()
        self.vocab = load_vocab(vocab_file)
        assert (0 < len(self.vocab))
        self.inv_vocab = {}
        self.control_len = 0
        for k, v in self.vocab.items():
            if v in control_tokens:
                self.control_len += 1  # Control characters are focused at the top?
            self.inv_vocab[v] = k

    def tokenize(self, text):
        split_tokens = self.tokenizer.tokenize(text)
        return split_tokens

    def convert_tokens_to_ids(self, tokens):
        return convert_by_vocab(self.vocab, tokens, unk_info=0)

    def convert_ids_to_tokens(self, ids):
        return convert_by_vocab(self.inv_vocab, ids, unk_info='[UNK]')

    # add for get random word
    def get_random_token(self):
        return self.inv_vocab[randint(self.control_len + 1, len(self.inv_vocab) - 1)]

    def __len__(self):
        return len(self.vocab)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='for MeCab Tokenizer vocab file generate.', usage='%(prog)s [options]')
    parser.add_argument('--file_path', help='Original text file path for creating vocab file.', required=True,
                        type=str)
    parser.add_argument('--vocab_path', help='Output vocab file path.', required=True,
                        type=str)
    parser.add_argument('--min_freq', help='Word appearance frequency adopted as vocabulary', nargs='?',
                        type=int, default=1)
    parser.add_argument('--limit_vocab_length', help='Word appearance frequency adopted as vocabulary', nargs='?',
                        type=int, default=-1)
    args = parser.parse_args()
    print('created : ' + args.vocab_path + ' , size :' + str(
        create_vocab(args.file_path, args.vocab_path, args.min_freq, args.limit_vocab_length)))
