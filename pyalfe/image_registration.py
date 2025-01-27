import logging
import os
import shutil
from abc import ABC, abstractmethod

from pyalfe.interfaces.greedy import Greedy
from pyalfe.tools import GREEDY_PATH

try:
    import ants
except ImportError:
    pass


class ImageRegistration(ABC):

    @abstractmethod
    def register_rigid(
        self,
        fixed,
        moving,
        transform_output,
        init_transform
    ):
        pass

    @abstractmethod
    def register_affine(
        self,
        fixed,
        moving,
        transform_output,
        init_transform,
        fast=False
    ):
        pass

    @abstractmethod
    def register_deformable(
        self,
        fixed,
        moving,
        transform_output,
        affine_transform=None
    ):
        pass

    @abstractmethod
    def reslice(
        self,
        fixed,
        moving,
        registration_output,
        *transform
    ):
        pass


class GreedyRegistration(ImageRegistration):
    logger = logging.getLogger('GreedyRegistration')

    def __init__(self, greedy_path=GREEDY_PATH, threads=16):
        self.greedy_path = greedy_path
        self.threads = threads

    def reslice(
            self,
            fixed,
            moving,
            registration_output,
            *transform):
        cmd = Greedy(self.greedy_path)
        cmd = cmd.dim(3).threads(self.threads)
        cmd = cmd.reslice(*transform).reference(fixed)
        cmd = cmd.input_output(moving, registration_output)
        cmd.run()

    def _register_affine(
            self,
            dof,
            fixed,
            moving,
            transform_output,
            init_transform,
            fast
    ):
        cmd = Greedy(self.greedy_path)
        if 'WNCC' in cmd.run():
            metric = 'WNCC'
        else:
            metric = 'NCC'
            self.logger.warning(
                'Your version of greedy does not support weigthed normalized'
                ' cross-correlation. Falling back to simple normalized'
                ' cross-correlation. Consider upgrading greedy to the'
                ' latest version.')
        if init_transform:
            cmd.initialize_affine(init_transform)
        cmd = cmd.threads(self.threads).dim(3).affine().dof(dof)
        cmd = cmd.metric(metric, 2)
        if fast:
            cmd = cmd.num_iter(100, 50, 0)
        else:
            cmd = cmd.num_iter(200, 100, 50)
        cmd = cmd.image_centers().input(fixed, moving).out(transform_output)
        cmd.run()
        return transform_output

    def register_rigid(
            self,
            fixed,
            moving,
            transform_output,
            init_transform=None
    ):
        return self._register_affine(
            6, fixed, moving, transform_output, init_transform, fast=False
        )

    def register_affine(
            self,
            fixed,
            moving,
            transform_output,
            init_transform=None,
            fast=True
    ):
        return self._register_affine(
            12, fixed, moving, transform_output, init_transform, fast
        )

    def register_deformable(
            self,
            fixed,
            moving,
            transform_output,
            affine_transform=None,

    ):
        if not affine_transform:
            fixed_name = os.path.basename(fixed).split('.')[0]
            moving_name = os.path.basename(moving).split('.')[0]
            affine_transform = os.path.join(
                os.path.dirname(transform_output),
                f'{moving_name}_to_{fixed_name}.mat')
            self.register_affine(fixed, moving, affine_transform, fast=False)
        if not os.path.exists(affine_transform):
            self.register_affine(fixed, moving, affine_transform, fast=False)

        cmd = Greedy(self.greedy_path)
        cmd = cmd.dim(3).threads(self.threads).metric('NCC', 2)
        cmd = cmd.epsilon(0.5).num_iter(100, 50, 10)
        if affine_transform:
            cmd = cmd.transforms(affine_transform)
        cmd.input(fixed, moving).out(transform_output)
        cmd.run()

class AntsRegistration(ImageRegistration):

    def reslice(self, fixed, moving, registration_output, *transform):
        fixed_image = ants.image_read(fixed)
        moving_image = ants.image_read(moving)
        output = ants.apply_transforms(fixed_image, moving_image, transform)
        ants.image_write(output, registration_output)

    def _register_affine(
        self,
        type_of_transform,
        fixed,
        moving,
        transform_output,
        init_transform
    ):
        if not transform_output:
            fixed_name = os.path.basename(fixed).split('.')[0]
            moving_name = os.path.basename(moving).split('.')[0]
            transform_output = f'{moving_name}_to_{fixed_name}.mat'
        rigid_output = ants.registration(
            ants.image_read(fixed), ants.image_read(moving),
            type_of_transform=type_of_transform,
            initial_transform=init_transform,
            reg_iterations=(100, 50, 10), verbose=True,  flow_sigma=1)
        shutil.copy(rigid_output['fwdtransforms'][0], transform_output)

    def register_rigid(
        self,
        fixed,
        moving,
        transform_output=None,
        init_transform=None
    ):
        self._register_affine(
            'DenseRigid', fixed, moving,
            transform_output, init_transform)

    def register_affine(
        self,
        fixed,
        moving,
        transform_output=None,
        init_transform=None,
        fast=False
    ):
        if fast:
            self._register_affine(
                'AffineFast', fixed, moving,
                transform_output, init_transform)
        else:
            self._register_affine(
                'TRSAA', fixed, moving,
                transform_output, init_transform)

    def register_deformable(
        self,
        fixed,
        moving,
        transform_output=None,
        affine_transform=None
    ):
        fixed_image = ants.image_read(fixed)
        moving_image = ants.image_read(moving)

        if not affine_transform:
            fixed_name = os.path.basename(fixed).split('.')[0]
            moving_name = os.path.basename(moving).split('.')[0]
            affine_transform = f'{moving_name}_to_{fixed_name}.mat'
            deformable_output = ants.registration(
                fixed_image, moving_image, 'SyN')
            shutil.copy(
                deformable_output['fwdtransforms'][1], affine_transform)
            shutil.copy(
                deformable_output['fwdtransforms'][0], transform_output
            )

        if not os.path.exists(affine_transform):
            deformable_output = ants.registration(
                fixed_image, moving_image, 'SyN')
            shutil.copy(
                deformable_output['fwdtransforms'][1], affine_transform)
            shutil.copy(
                deformable_output['fwdtransforms'][0], transform_output
            )
        else:
            deformable_output = ants.registration(
                fixed_image, moving_image, 'SyNOnly',
                initial_transform=affine_transform
            )
            shutil.copy(
                deformable_output['fwdtransforms'][0], transform_output
            )
