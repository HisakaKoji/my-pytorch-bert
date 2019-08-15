# coding=utf-8
#
# Author Toshihiko Aoki
# This file is based on
# https://raw.githubusercontent.com/huggingface/pytorch-pretrained-BERT/master/pytorch_pretrained_bert/optimization.py.
# Change decoy effort variables method (original google impl use),
# and modify update lr method,
# and add get_step method.
#
# Copyright 2018 The Google AI Language Team Authors and The HugginFace Inc. team.
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
"""PyTorch optimization for BERT model."""

import re

import torch
from torch.optim import Optimizer
from torch.optim.optimizer import required
from torch.nn.utils import clip_grad_norm_


class BertAdam(Optimizer):
    """Implements BERT version of Adam algorithm with weight decay fix.
    Params:
        lr: learning rate
        warmup_steps: total number of warmup steps. 0 means polynomial decay learning rate. Default: 0
        max_steps: total number of max steps. 0  means constant learning rate. Default: 0
        b1: Adams b1. Default: 0.9
        b2: Adams b2. Default: 0.999
        e: Adams epsilon. Default: 1e-6
        max_grad_norm: Maximum norm for the gradients (-1 means no clipping). Default: 1.0
    """
    def __init__(self, params, lr=required, warmup_steps=0, max_steps=0,
                 b1=0.9, b2=0.999, e=1e-6, max_grad_norm=1.0):
        if lr is not required and lr < 0.0:
            raise ValueError("Invalid learning rate: {} - should be >= 0.0".format(lr))
        if warmup_steps < 0:
            raise ValueError("Invalid warmup_steps parameter: {} - should be >= 0".format(warmup_steps))
        if max_steps < 0:
            raise ValueError("Invalid max_steps parameter: {} - should be >= 0".format(max_steps))
        if not 0.0 <= b1 < 1.0:
            raise ValueError("Invalid b1 parameter: {} - should be in [0.0, 1.0]".format(b1))
        if not 0.0 <= b2 < 1.0:
            raise ValueError("Invalid b2 parameter: {} - should be in [0.0, 1.0]".format(b2))
        if not e >= 0.0:
            raise ValueError("Invalid epsilon value: {} - should be >= 0.0".format(e))
        defaults = dict(lr=lr, warmup_steps=warmup_steps, max_steps=max_steps,
                        b1=b1, b2=b2, e=e, max_grad_norm=max_grad_norm)
        super(BertAdam, self).__init__(params, defaults)

    def step(self, closure=None):
        """Performs a single optimization step.
        Arguments:
            closure (callable, optional): A closure that reevaluates the model
                and returns the loss.
        """
        loss = None
        if closure is not None:
            loss = closure()

        for group in self.param_groups:
            for p in group['params']:
                if p.grad is None:
                    continue
                grad = p.grad.data
                if grad.is_sparse:
                    raise RuntimeError('Adam does not support sparse gradients, please consider SparseAdam instead')

                state = self.state[p]

                # State initialization
                if len(state) is 0:
                    state['step'] = 0
                    # Exponential moving average of gradient values
                    state['next_m'] = torch.zeros_like(p.data)
                    # Exponential moving average of squared gradient values
                    state['next_v'] = torch.zeros_like(p.data)

                next_m, next_v = state['next_m'], state['next_v']

                beta1, beta2 = group['b1'], group['b2']

                # Add grad clipping
                if group['max_grad_norm'] > 0:
                    clip_grad_norm_(p, group['max_grad_norm'])

                # Decay the first and second moment running average coefficient
                # In-place operations to update the averages at the same time
                next_m.mul_(beta1).add_(1 - beta1, grad)
                next_v.mul_(beta2).addcmul_(1 - beta2, grad, grad)
                update = next_m / (next_v.sqrt() + group['e'])

                # Just adding the square of the weights to the loss function is *not*
                # the correct way of using L2 regularization/weight decay with Adam,
                # since that will interact with the m and v parameters in strange ways.
                #
                # Instead we want to decay the weights in a manner that doesn't interact
                # with the m/v parameters. This is equivalent to adding the square
                # of the weights to the loss with plain (non-momentum) SGD.
                if group['weight_decay'] > 0.0:
                    update += group['weight_decay'] * p.data

                lr_scheduled = update_lr(state['step'], group['lr'], group['warmup_steps'], group['max_steps'])

                update_with_lr = lr_scheduled * update
                p.data.add_(-update_with_lr)

                state['step'] += 1

        return loss

    # add for continue optimization steps
    def get_step(self):
        state = self.state[((self.param_groups[0])['params'])[0]]
        if 'step' in state:
            return state['step']
        return 0


def update_lr(step, lr=5e-5, warmup_steps=0, max_steps=0):
    if step < 0:
        return lr
    if warmup_steps is not 0 and step < warmup_steps:
        return lr * step / warmup_steps
    elif max_steps is not 0:
        global_step = min(step, max_steps)
        return lr * (1 - global_step / max_steps)
    else:
        return lr


def update_lr_apex(optimzer, step, lr=5e-5, warmup_steps=0, max_steps=0):
    for param_group in optimzer.param_groups:
        param_group['lr'] = update_lr(step, lr, warmup_steps, max_steps)


# add for optimizer initializer
def get_optimizer(
        model,
        lr=5e-5,
        warmup_steps=0,
        max_steps=0,
        decoy=0.01,
        no_decay=('bias', 'layer_norm', 'LayerNorm'),
        fp16=False
):
    param_optimizer = list(model.named_parameters())
    optimizer_grouped_parameters = [
        {'params': [p for n, p in param_optimizer if _do_use_weight_decay(n, no_decay)], 'weight_decay': decoy},
        {'params': [p for n, p in param_optimizer if not _do_use_weight_decay(n, no_decay)], 'weight_decay': 0.0}
    ]
    if fp16:
        try:
            from apex.optimizers import FP16_Optimizer
            from apex.optimizers import FusedAdam
            from torch._utils import _flatten_dense_tensors, _unflatten_dense_tensors

            optimizer = FusedAdam(optimizer_grouped_parameters,
                                  lr=lr,
                                  bias_correction=False,
                                  max_grad_norm=1.0)

            def get_step(self):
                state = self.optimizer.state[((self.optimizer.param_groups[0])['params'])[0]]
                if 'step' in state:
                    return state['step']
                return 0

            def step(self, closure=None):
                """
                Not supporting closure.
                """
                # First compute norm for all group so we know if there is overflow
                grads_groups_flat = []
                norm_groups = []
                skip = False
                for i, group in enumerate(self.fp16_groups):
                    # https://github.com/NVIDIA/apex/issues/131
                    grads_groups_flat.append(
                        _flatten_dense_tensors(
                            [p.grad if p.grad is not None else p.new_zeros(p.size()) for p in group]))
                    # grads_groups_flat.append(_flatten_dense_tensors([p.grad for p in group]))
                    norm_groups.append(self.compute_grad_norm(grads_groups_flat[i]))
                    if norm_groups[i] == -1:  # TODO: early break
                        skip = True

                if skip:
                    self._update_scale(skip)
                    return

                # norm is in fact norm*cur_scale
                self.optimizer.step(grads=[[g] for g in grads_groups_flat],
                                    output_params=[[p] for p in self.fp16_groups_flat],
                                    scale=self.cur_scale,
                                    grad_norms=norm_groups)

                # TODO: we probably don't need this? just to be safe
                for i in range(len(norm_groups)):
                    updated_params = _unflatten_dense_tensors(self.fp16_groups_flat[i], self.fp16_groups[i])
                    for p, q in zip(self.fp16_groups[i], updated_params):
                        p.data = q.data

                self._update_scale(False)
                return

            FP16_Optimizer.get_step = get_step
            FP16_Optimizer.step = step
            return FP16_Optimizer(optimizer, dynamic_loss_scale=False)
        except ImportError:
            raise ImportError(
                "Please install apex from https://www.github.com/nvidia/apex to use fp16 training.")
    else:
        return BertAdam(optimizer_grouped_parameters, lr, warmup_steps, max_steps)


def _do_use_weight_decay(param_name, exclude_from_weight_decay):
    """Whether to use L2 weight decay for `param_name`."""
    if exclude_from_weight_decay:
        for r in exclude_from_weight_decay:
            if re.search(r, param_name) is not None:
                return False
    return True

