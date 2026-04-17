# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class CoastalInputs(BaseModel):
    sessionid: str = Field(min_length=1)


class HazardInputs(BaseModel):
    name: str = Field(min_length=1)
    hazard: Literal['flood', 'drought', 'erosion', 'heat', 'fire']


class UomInputs(BaseModel):
    sessionid: str = Field(min_length=1)
    uomsize: int
    layername: str = Field(min_length=1)
    id: str = Field(min_length=1)
    archetype: Literal['coastal', 'urban', 'rural']


class UomKcsInputs(BaseModel):
    sessionid: str = Field(min_length=1)
    kcs: str = Field(min_length=1)
    hazard: str = Field(min_length=1)
    archetype: str = Field(min_length=1)

    @model_validator(mode='after')
    def hazard_in_config(self) -> Self:
        from processes.config import get_config
        cfg = get_config()
        if self.hazard not in cfg.hazard_layers:
            available = list(cfg.hazard_layers.keys())
            raise ValueError(
                f'Hazard {self.hazard!r} not found in config hazard_layers. '
                f'Available: {available}'
            )
        return self
