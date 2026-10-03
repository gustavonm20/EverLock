"""Leitura de rostos com OpenCV: detector YuNet e reconhecedor SFace.

O motor recebe os bytes de UMA imagem (JPEG ou PNG), confirma que há exatamente um rosto de boa
qualidade e devolve um vetor de 128 números. A imagem existe só na memória durante a chamada:
nada é gravado em disco. Quem decide se dois vetores são da mesma pessoa é o módulo de
reconhecimento, não este.
"""

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DETECTOR_MODEL = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = "face_recognition_sface_2021dec.onnx"
MODEL_URLS = {
    DETECTOR_MODEL: "https://github.com/opencv/opencv_zoo/raw/main/models/"
                    "face_detection_yunet/face_detection_yunet_2023mar.onnx",
    RECOGNIZER_MODEL: "https://github.com/opencv/opencv_zoo/raw/main/models/"
                      "face_recognition_sface/face_recognition_sface_2021dec.onnx",
}

# Limites provisórios de qualidade. Precisam ser calibrados com imagens autorizadas do grupo.
MIN_DETECTION_SCORE = 0.90
MIN_FACE_PIXELS = 80
MIN_SHARPNESS = 20.0
MAX_IMAGE_BYTES = 1_500_000
MAX_SIDE = 1280


class FaceError(Exception):
    """Imagem inutilizável para reconhecimento. `code` é estável; `message` vai ao usuário."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class FaceReading:
    embedding: tuple[float, ...]
    face_pixels: int
    detection_score: float
    sharpness: float
    # Giro do rosto: 0 = de frente; positivo = virado para a esquerda da própria pessoa
    # (nariz desloca para a direita da imagem); negativo = para a direita.
    yaw: float = 0.0


class FaceEngine(Protocol):
    available: bool
    reason: str
    model_id: str

    def read(self, image: bytes) -> FaceReading: ...


class UnavailableEngine:
    available, model_id = False, "nenhum"

    def __init__(self, reason: str):
        self.reason = reason

    def read(self, image: bytes) -> FaceReading:
        raise FaceError("engine_unavailable", self.reason)


class OpenCVFaceEngine:
    model_id = "yunet-2023mar+sface-2021dec"

    def __init__(self, models_dir: Path):
        self.models_dir = Path(models_dir)
        self.available, self.reason = False, ""
        self._lock = threading.Lock()
        self._detector = self._recognizer = self._cv2 = self._np = None
        self._load()

    def _load(self) -> None:
        try:
            import cv2
            import numpy
        except ImportError:
            self.reason = ("A biblioteca OpenCV não está instalada. Rode .\\iniciar.cmd "
                           "para instalar as dependências.")
            return
        missing = [name for name in (DETECTOR_MODEL, RECOGNIZER_MODEL)
                   if not (self.models_dir / name).is_file()]
        if missing:
            self.reason = ("Modelos de reconhecimento ausentes. Rode "
                           "python scripts\\baixar_modelos.py (veja docs/facial-recognition.md).")
            return
        try:
            self._detector = cv2.FaceDetectorYN.create(
                str(self.models_dir / DETECTOR_MODEL), "", (320, 320),
                MIN_DETECTION_SCORE, 0.3, 5000,
            )
            self._recognizer = cv2.FaceRecognizerSF.create(
                str(self.models_dir / RECOGNIZER_MODEL), "",
            )
        except cv2.error as error:
            self.reason = f"Os modelos não puderam ser carregados: {error.msg or 'erro do OpenCV'}"
            return
        self._cv2, self._np = cv2, numpy
        self.available = True

    def read(self, image: bytes) -> FaceReading:
        if not self.available:
            raise FaceError("engine_unavailable", self.reason)
        if len(image) > MAX_IMAGE_BYTES:
            raise FaceError("invalid_image", "A imagem é grande demais.")
        cv2, np = self._cv2, self._np
        frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise FaceError("invalid_image", "Não foi possível ler a imagem enviada.")
        height, width = frame.shape[:2]
        if max(height, width) > MAX_SIDE:
            scale = MAX_SIDE / max(height, width)
            frame = cv2.resize(frame, (round(width * scale), round(height * scale)))
            height, width = frame.shape[:2]
        with self._lock:  # os objetos do OpenCV não são seguros entre threads
            self._detector.setInputSize((width, height))
            _, found = self._detector.detect(frame)
            faces = [] if found is None else [row for row in found
                                              if row[14] >= MIN_DETECTION_SCORE]
            if not faces:
                raise FaceError("no_face", "Nenhum rosto foi encontrado. Fique de frente para a "
                                           "câmera, com boa iluminação.")
            if len(faces) > 1:
                raise FaceError("multiple_faces", "Há mais de um rosto na imagem. Apenas uma "
                                                  "pessoa deve aparecer.")
            face = faces[0]
            if face[2] < MIN_FACE_PIXELS:
                raise FaceError("face_too_small", "O rosto está longe ou pequeno demais. "
                                                  "Aproxime-se da câmera.")
            eye_gap = float(face[6] - face[4])  # olho esquerdo - olho direito, em pixels
            if eye_gap < 1.0:
                raise FaceError("no_face", "Não foi possível medir o rosto. Fique de frente, "
                                            "com boa iluminação.")
            yaw = float((face[8] - (face[4] + face[6]) / 2) / eye_gap)
            aligned = self._recognizer.alignCrop(frame, face)
            sharpness = float(cv2.Laplacian(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY),
                                            cv2.CV_64F).var())
            if sharpness < MIN_SHARPNESS:
                raise FaceError("blurry", "A imagem está tremida ou fora de foco. Fique parado "
                                          "e tente de novo.")
            feature = self._recognizer.feature(aligned)
        return FaceReading(
            embedding=tuple(float(value) for value in feature.reshape(-1)),
            face_pixels=int(face[2]), detection_score=float(face[14]), sharpness=sharpness,
            yaw=yaw,
        )
