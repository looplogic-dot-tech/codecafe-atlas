from __future__ import annotations

import getpass
import hashlib
import json
import os
import platform
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from . import __version__
from .identity import AUTHOR_NAME, BRAND_NAME, CONTACT_EMAIL, PRODUCT_NAME
from .paths import data_dir


AGREEMENT_VERSION = "2026-08-29.1"

AGREEMENT_ES = f"""ACUERDO DE LICENCIA DE USO DE {PRODUCT_NAME.upper()}
Versión del acuerdo: {AGREEMENT_VERSION}

AVISO IMPORTANTE
Este acuerdo regula el uso de {PRODUCT_NAME}. La aceptación no vende ni transfiere la propiedad del software. La autorización efectiva depende también del certificado, orden de licencia o autorización escrita emitida por el Licenciante.

1. PARTES
Licenciante: {AUTHOR_NAME}, bajo la marca {BRAND_NAME} ("Licenciante").
Licenciatario: la organización identificada en el registro de aceptación y en el certificado u orden de licencia aplicable ("Licenciatario").
Usuario autorizado: la persona física autorizada por el Licenciatario y por el alcance de la licencia.

2. OTORGAMIENTO LIMITADO
Sujeto al cumplimiento de este acuerdo y a una autorización vigente, el Licenciante concede al Licenciatario un derecho limitado, revocable, no exclusivo, no transferible y no sublicenciable para utilizar {PRODUCT_NAME} exclusivamente en las instalaciones, territorio, periodo, número de usuarios y fines operativos expresamente autorizados. La aceptación de este texto, por sí sola, no amplía el alcance de la licencia.

3. PROPIEDAD DE ATLAS
{PRODUCT_NAME}, su código fuente y objeto, arquitectura, diseño, interfaces, documentación, módulos, plantillas propias, actualizaciones, marcas y demás componentes originales pertenecen al Licenciante. Ningún pago por alojamiento, implementación, soporte o desarrollo transfiere esos derechos salvo cesión expresa y separada firmada por el Licenciante.

El Licenciatario reconoce que no solicitó, encargó ni comisionó originalmente la creación de Atlas. El Licenciante lo inició por cuenta propia para facilitar y mejorar su flujo personal de trabajo. La tolerancia, demostración o autorización de uso de versiones anteriores no constituye encargo, venta, cesión ni transferencia de propiedad intelectual.

4. PROPIEDAD Y CONTROL DE LOS DATOS
El Licenciatario conserva la propiedad y el control de los datos operativos que su personal introduzca, importe o genere mediante el uso de Atlas. El Licenciante no adquiere propiedad sobre dichos datos. La aplicación deberá permitir su respaldo o exportación conforme a las funciones disponibles y a la autorización correspondiente.

5. RESTRICCIONES
Sin autorización previa y escrita del Licenciante, el Licenciatario y los usuarios no podrán: copiar o instalar Atlas fuera del alcance autorizado; entregar credenciales o copias a terceros; vender, sublicenciar, arrendar o redistribuir Atlas; retirar avisos de propiedad; acceder o intentar acceder al código fuente; eludir licencias o controles de acceso; ni modificar, descompilar, desensamblar o realizar ingeniería inversa, salvo en la medida estrictamente permitida por una disposición legal imperativa.

6. USUARIOS Y SEGURIDAD
Cada usuario deberá utilizar credenciales propias cuando Atlas disponga de autenticación. El Licenciatario es responsable de autorizar a su personal, retirar accesos oportunamente y proteger credenciales, equipos y copias de seguridad. La aceptación registrada identifica al usuario de la instalación, pero no sustituye el certificado organizacional de licencia.

7. ALOJAMIENTO E INFRAESTRUCTURA
Los costos de servidores, almacenamiento, tráfico, respaldos, dominios, certificados, servicios externos y demás infraestructura necesaria para una implementación web o de alcance ampliado serán cubiertos conforme a la orden de licencia o propuesta aceptada. El Licenciante no está obligado a financiar una implementación organizacional o nacional con recursos personales.

8. SOPORTE, CAMBIOS Y ACTUALIZACIONES
El soporte, mantenimiento, disponibilidad, niveles de servicio, capacitación, migración y desarrollo de nuevas funciones solo estarán incluidos cuando se establezcan expresamente en una propuesta, orden de licencia o contrato adicional. El Licenciante conserva la facultad de desarrollar y licenciar Atlas a terceros.

9. VIGENCIA Y TERMINACIÓN
La licencia permanecerá vigente durante el periodo indicado en la autorización aplicable. Al vencer, revocarse o terminar, deberá cesar el uso operativo de Atlas. El Licenciatario conservará sus datos y podrá obtener los respaldos o exportaciones disponibles. La terminación no autoriza al Licenciante a borrar, cifrar, apropiarse o alterar los datos del Licenciatario.

10. CONFIDENCIALIDAD Y CÓDIGO FUENTE
La entrega de una copia ejecutable no implica entrega del código fuente. El código fuente, claves de firma, mecanismos de licencia y materiales no públicos serán tratados como información reservada del Licenciante. Cualquier depósito, custodia o acceso excepcional al código fuente requerirá un acuerdo separado.

11. GARANTÍAS Y RESPONSABILIDAD
Atlas se proporciona conforme a las condiciones y alcance expresamente contratados. En la medida permitida por la legislación aplicable, ninguna parte responderá por daños indirectos, incidentales o pérdida de beneficios. Esta cláusula no limita responsabilidades que legalmente no puedan excluirse ni las obligaciones expresamente asumidas por escrito.

12. LEY APLICABLE Y CONTROVERSIAS
Este acuerdo se interpretará conforme a las leyes aplicables de los Estados Unidos Mexicanos. Las partes procurarán resolver cualquier diferencia mediante negociación escrita de buena fe antes de acudir a la autoridad competente. La orden de licencia podrá establecer jurisdicción, mediación o arbitraje específicos.

13. IDIOMA Y ACUERDO COMPLETO
Las versiones española e inglesa expresan el mismo acuerdo. En caso de discrepancia interpretativa, prevalecerá la versión en español. Este texto, junto con el certificado u orden de licencia aplicable, constituye el acuerdo de uso; cualquier cesión de propiedad intelectual deberá constar de manera expresa, separada y firmada.

14. ACEPTACIÓN
Al seleccionar la casilla de aceptación, el usuario declara que leyó ambas versiones, que está autorizado para utilizar la instalación en nombre de la organización indicada y que acepta cumplir este acuerdo. Para asuntos de licencia: {CONTACT_EMAIL}.
"""

AGREEMENT_EN = f"""{PRODUCT_NAME.upper()} SOFTWARE USE LICENSE AGREEMENT
Agreement version: {AGREEMENT_VERSION}

IMPORTANT NOTICE
This agreement governs the use of {PRODUCT_NAME}. Acceptance does not sell or transfer ownership of the software. Effective authorization also requires a valid license certificate, order form, or written authorization issued by the Licensor.

1. PARTIES
Licensor: {AUTHOR_NAME}, operating under the {BRAND_NAME} brand ("Licensor").
Licensee: the organization identified in the acceptance record and the applicable license certificate or order form ("Licensee").
Authorized User: an individual authorized by the Licensee and within the scope of the license.

2. LIMITED GRANT
Subject to compliance with this agreement and a current authorization, Licensor grants Licensee a limited, revocable, non-exclusive, non-transferable, and non-sublicensable right to use {PRODUCT_NAME} solely at the locations, within the territory and period, for the number of users, and for the operational purposes expressly authorized. Acceptance of this text alone does not expand the license scope.

3. OWNERSHIP OF ATLAS
{PRODUCT_NAME}, including its source and object code, architecture, design, interfaces, documentation, modules, proprietary templates, updates, trademarks, and other original components, remains the property of Licensor. Payment for hosting, implementation, support, or development does not transfer those rights unless Licensor signs an express and separate assignment.

Licensee acknowledges that it did not originally request, commission, or direct the creation of Atlas. Licensor initiated Atlas independently to facilitate and improve Licensor's personal workflow. Tolerance, demonstration, or authorization to use earlier versions does not constitute a commission, sale, assignment, or transfer of intellectual-property ownership.

4. OWNERSHIP AND CONTROL OF DATA
Licensee retains ownership and control of the operational data entered, imported, or generated by its personnel through Atlas. Licensor acquires no ownership of that data. The application shall permit backup or export according to the available functionality and applicable authorization.

5. RESTRICTIONS
Without Licensor's prior written authorization, Licensee and users may not: copy or install Atlas beyond the authorized scope; provide credentials or copies to third parties; sell, sublicense, lease, or redistribute Atlas; remove ownership notices; access or attempt to access source code; circumvent licensing or access controls; or modify, decompile, disassemble, or reverse engineer Atlas, except to the limited extent required by mandatory law.

6. USERS AND SECURITY
Each user shall use individual credentials whenever Atlas provides authentication. Licensee is responsible for authorizing personnel, promptly removing access, and protecting credentials, equipment, and backups. The recorded acceptance identifies the installation user but does not replace the organizational license certificate.

7. HOSTING AND INFRASTRUCTURE
Server, storage, traffic, backup, domain, certificate, external service, and other infrastructure costs required for a web or expanded deployment shall be paid as specified in the accepted proposal or license order. Licensor is not required to personally finance an organizational or nationwide deployment.

8. SUPPORT, CHANGES, AND UPDATES
Support, maintenance, availability, service levels, training, migration, and new development are included only when expressly stated in a proposal, license order, or additional agreement. Licensor retains the right to develop and license Atlas to third parties.

9. TERM AND TERMINATION
The license remains effective for the period stated in the applicable authorization. Upon expiration, revocation, or termination, operational use of Atlas must cease. Licensee retains its data and may obtain available backups or exports. Termination does not authorize Licensor to delete, encrypt, appropriate, or alter Licensee data.

10. CONFIDENTIALITY AND SOURCE CODE
Delivery of an executable copy does not include delivery of source code. Source code, signing keys, licensing mechanisms, and non-public materials shall be treated as Licensor's confidential information. Any escrow, custody, or exceptional source access requires a separate agreement.

11. WARRANTIES AND LIABILITY
Atlas is provided according to the conditions and scope expressly contracted. To the extent permitted by applicable law, neither party shall be liable for indirect or incidental damages or lost profits. This clause does not limit liability that cannot legally be excluded or obligations expressly accepted in writing.

12. GOVERNING LAW AND DISPUTES
This agreement shall be interpreted under the applicable laws of the United Mexican States. The parties shall first attempt to resolve disputes through good-faith written negotiation before applying to the competent authority. The license order may establish specific jurisdiction, mediation, or arbitration.

13. LANGUAGE AND ENTIRE AGREEMENT
The Spanish and English versions express the same agreement. If an interpretive discrepancy arises, the Spanish version controls. This text and the applicable license certificate or order form form the use agreement; any intellectual-property assignment must be express, separate, and signed.

14. ACCEPTANCE
By selecting the acceptance checkbox, the user declares that both versions have been read, that the user is authorized to use the installation on behalf of the identified organization, and that the user agrees to comply with this agreement. License contact: {CONTACT_EMAIL}.
"""


def agreement_hash() -> str:
    canonical = f"{AGREEMENT_VERSION}\n{AGREEMENT_ES}\n{AGREEMENT_EN}".encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def acceptance_path() -> Path:
    return data_dir() / "license_acceptances.json"


def _os_user() -> str:
    return (getpass.getuser() or os.environ.get("USERNAME") or "unknown").strip()


def _load_acceptances() -> list[dict]:
    path = acceptance_path()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def current_user_has_accepted() -> bool:
    expected_hash = agreement_hash()
    current_user = _os_user().casefold()
    return any(
        str(item.get("agreement_version") or "") == AGREEMENT_VERSION
        and str(item.get("agreement_sha256") or "") == expected_hash
        and str(item.get("os_user") or "").casefold() == current_user
        for item in _load_acceptances()
        if isinstance(item, dict)
    )


def _write_acceptance(full_name: str, organization: str, language: str) -> None:
    path = acceptance_path()
    records = _load_acceptances()
    current_user = _os_user()
    records = [
        item for item in records
        if not (
            isinstance(item, dict)
            and str(item.get("os_user") or "").casefold() == current_user.casefold()
            and str(item.get("agreement_version") or "") == AGREEMENT_VERSION
        )
    ]
    records.append({
        "agreement_version": AGREEMENT_VERSION,
        "agreement_sha256": agreement_hash(),
        "accepted_at_utc": datetime.now(timezone.utc).isoformat(),
        "full_name": full_name.strip(),
        "organization": organization.strip(),
        "language_viewed": language,
        "os_user": current_user,
        "computer_name": socket.gethostname(),
        "platform": platform.platform(),
        "atlas_version": __version__,
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="license_acceptances_", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


class UseAgreementDialog(QDialog):
    def __init__(self, *, acceptance_required: bool, parent=None):
        super().__init__(parent)
        self.acceptance_required = acceptance_required
        self.setWindowTitle(f"Licencia de uso / Software License - {PRODUCT_NAME}")
        self.resize(900, 720)
        self.setMinimumSize(720, 560)

        layout = QVBoxLayout(self)
        title = QLabel(f"<b>Licencia de uso de {PRODUCT_NAME}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)

        notice = QLabel(
            "El Licenciatario conserva sus datos operativos. CodeCafe conserva la propiedad de Atlas. "
            "La aceptación no constituye una cesión del software."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        self.language = QComboBox()
        self.language.addItem("Español", "es")
        self.language.addItem("English", "en")
        self.language.currentIndexChanged.connect(self._refresh_text)
        layout.addWidget(self.language)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.text, 1)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Nombre completo / Full name")
        self.organization = QLineEdit()
        self.organization.setPlaceholderText("Organización autorizada / Authorized organization")
        form = QFormLayout()
        form.addRow("Usuario / User:", self.name)
        form.addRow("Organización / Organization:", self.organization)
        layout.addLayout(form)

        self.confirm = QCheckBox(
            "He leído y acepto el acuerdo; declaro estar autorizado para usar esta instalación. / "
            "I have read and accept the agreement and confirm I am authorized to use this installation."
        )
        layout.addWidget(self.confirm)

        buttons = (
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            if acceptance_required
            else QDialogButtonBox.StandardButton.Close
        )
        self.button_box = QDialogButtonBox(buttons)
        if acceptance_required:
            self.accept_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
            self.accept_button.setText("Aceptar y continuar / Accept and continue")
            self.accept_button.setEnabled(False)
            self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(
                "No aceptar y salir / Decline and exit"
            )
            self.button_box.accepted.connect(self._accept)
            self.button_box.rejected.connect(self.reject)
            self.name.textChanged.connect(self._update_accept_state)
            self.organization.textChanged.connect(self._update_accept_state)
            self.confirm.toggled.connect(self._update_accept_state)
        else:
            self.name.setVisible(False)
            self.organization.setVisible(False)
            self.confirm.setVisible(False)
            for label in self.findChildren(QLabel):
                if label.text() in {"Usuario / User:", "Organización / Organization:"}:
                    label.setVisible(False)
            self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self._refresh_text()

    def _refresh_text(self) -> None:
        self.text.setPlainText(AGREEMENT_ES if self.language.currentData() == "es" else AGREEMENT_EN)
        self.text.moveCursor(QTextCursor.MoveOperation.Start)

    def _update_accept_state(self) -> None:
        if not self.acceptance_required:
            return
        self.accept_button.setEnabled(
            bool(self.name.text().strip())
            and bool(self.organization.text().strip())
            and self.confirm.isChecked()
        )

    def _accept(self) -> None:
        try:
            _write_acceptance(
                self.name.text(), self.organization.text(), self.language.currentData()
            )
        except OSError as error:
            QMessageBox.critical(
                self,
                "No fue posible registrar la aceptación",
                f"Atlas no pudo guardar el registro de aceptación:\n{error}",
            )
            return
        self.accept()


def ensure_use_agreement(parent=None) -> bool:
    if current_user_has_accepted():
        return True
    return UseAgreementDialog(acceptance_required=True, parent=parent).exec() == QDialog.DialogCode.Accepted


def show_use_agreement(parent=None) -> None:
    UseAgreementDialog(acceptance_required=False, parent=parent).exec()
