"""Equivalent batched inference for the Mega53 depth-two mask estimators.

The learned layers, activations and output order are unchanged. Batching heads
reduces thousands of small matrix calls without discarding instrument heads.
"""
import torch
from torch import nn
from torch.nn import functional as F


class MaskBand(nn.Module):
    def __init__(self, estimators, band):
        super().__init__()
        networks=[head.to_freqs[band] for head in estimators]
        for network in networks:
            layers=network[0]
            if (len(layers)!=3 or not isinstance(layers[0],nn.Linear)
                or not isinstance(layers[1],nn.Tanh) or not isinstance(layers[2],nn.Linear)
                or not isinstance(network[1],nn.GLU) or network[1].dim!=-1):
                raise ValueError('Unsupported estimator architecture')
        self.register_buffer('w1',torch.stack([n[0][0].weight.detach() for n in networks]))
        self.register_buffer('b1',torch.stack([n[0][0].bias.detach() for n in networks]))
        self.register_buffer('w2',torch.stack([n[0][2].weight.detach() for n in networks]))
        self.register_buffer('b2',torch.stack([n[0][2].bias.detach() for n in networks]))

    def forward(self, x, ids=None):
        w1,b1,w2,b2=self.w1,self.b1,self.w2,self.b2
        if ids is not None:w1,b1,w2,b2=w1[ids],b1[ids],w2[ids],b2[ids]
        heads,hidden,dim=w1.shape
        batch,times,_=x.shape
        y=torch.tanh(F.linear(x,w1.reshape(heads*hidden,dim),b1.reshape(-1)))
        y=y.reshape(batch,times,heads,hidden).permute(2,0,1,3).reshape(heads,batch*times,hidden)
        y=torch.bmm(y,w2.transpose(1,2))+b2[:,None,:]
        y=y.reshape(heads,batch,times,w2.shape[1]).permute(1,0,2,3)
        return F.glu(y,dim=-1)


class FusedMaskBank(nn.Module):
    def __init__(self, estimators):
        super().__init__()
        self.bands=nn.ModuleList([MaskBand(estimators,i) for i in range(len(estimators[0].to_freqs))])

    def forward(self, x, active_stem_ids=None):
        ids=None if active_stem_ids is None else torch.as_tensor(active_stem_ids,device=x.device,dtype=torch.long)
        return torch.cat([band(x[:,:,index],ids) for index,band in enumerate(self.bands)],dim=-1)


def enable(model):
    """Convert only the supported evaluation graph, releasing copied modules."""
    if model.training:raise ValueError('Fused masks are inference-only')
    bank=FusedMaskBank(model.mask_estimators)
    model.fast_mask_bank=bank
    del model.mask_estimators
    return model
