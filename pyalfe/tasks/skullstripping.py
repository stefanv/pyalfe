import logging
import os

from pyalfe.data_structure import Modality, PipelineDataDir
from pyalfe.image_processing import ImageProcessor
from pyalfe.inference import InferenceModel
from pyalfe.tasks import Task


class Skullstripping(Task):

    logger = logging.getLogger('Skullstripping')

    def __init__(self,
                 inference_model: InferenceModel,
                 image_processor: ImageProcessor,
                 pipeline_dir: PipelineDataDir,
                 modalities: list[Modality],
                 overwrite: bool=True):
        self.inference_model = inference_model
        self.image_processor = image_processor
        self.pipeline_dir = pipeline_dir
        self.modalities = modalities
        self.overwrite = overwrite

    def process_modalities(self, accession, modalities):
        images_tuple_list = []
        pred_list = []
        mask_list = []
        output_list = []
        for modality in modalities:
            image = self.pipeline_dir.get_processed_image(
                accession, modality)
            pred = self.pipeline_dir.get_processed_image(
                accession, modality, image_type='skullstripping_pred')
            mask = self.pipeline_dir.get_processed_image(
                accession, modality, image_type='skullstripping_mask')
            output = self.pipeline_dir.get_processed_image(
                accession, modality, image_type='skullstripped')
            if not self.overwrite and os.path.exists(output):
                continue
            images_tuple_list.append((image,))
            pred_list.append(pred)
            mask_list.append(mask)
            output_list.append(output)
        if not images_tuple_list:
            return
        self.inference_model.predict_cases(images_tuple_list, pred_list)
        for image_tuple, pred, mask, output in zip(
                images_tuple_list, pred_list, mask_list, output_list):
            image = image_tuple[0]
            self.image_processor.largest_mask_comp(pred, mask)
            self.image_processor.mask(image, mask, output)

    def run(self, accession):
        modalities_to_process = []
        for modality in self.modalities:
            image = self.pipeline_dir.get_processed_image(
                accession, modality)
            if not os.path.exists(image):
                self.logger.info(
                    f'{modality} image is missing.'
                    f'Skipping skullstripping for {modality}')
                continue
            modalities_to_process.append(modality)
        self.process_modalities(accession, modalities_to_process)
