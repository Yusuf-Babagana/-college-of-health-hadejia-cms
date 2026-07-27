from .applicant import Applicant, ReferralCode
from .application import (
    Application,
    SchoolAttended,
    SSCESitting,
    SSCESubjectResult,
    UploadedDocument,
)
from .payment import AdmissionPayment
from .programme import Programme

__all__ = [
    'Applicant',
    'ReferralCode',
    'Programme',
    'AdmissionPayment',
    'Application',
    'SchoolAttended',
    'SSCESitting',
    'SSCESubjectResult',
    'UploadedDocument',
]
