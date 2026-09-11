from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


_HARD_CLEAR_HISTORY_JS = r"""
(() => {
  const REQUIRED_PHRASE = 'BORRAR HISTORIAL';

  window.clearHistory = async function() {
    const count = Array.isArray(state.history) ? state.history.length : 0;
    if (!count) return;

    const typed = window.prompt(
      `PELIGRO: vas a borrar ${count} registro(s) históricos de contadores.\n\n` +
      `Esta acción no se puede deshacer.\n\n` +
      `Escribe exactamente ${REQUIRED_PHRASE} para continuar:`
    );

    if (typed === null) return;
    if (String(typed).trim() !== REQUIRED_PHRASE) {
      window.alert('Confirmación incorrecta. No se borró ningún registro.');
      return;
    }

    if (!window.confirm(
      `Última confirmación: ¿borrar definitivamente ${count} registro(s) de contadores?`
    )) return;

    if (state.dbBridge) {
      try {
        const result = await bridgeCall('clearRecords');
        if (result && result.ok === false) {
          throw new Error(result.error || 'La base común rechazó la operación.');
        }
      } catch (error) {
        window.alert(`No se pudo borrar la base común: ${error.message || error}`);
        return;
      }
    }

    state.history = [];
    persistHistory();
    renderHistory();
    setDatabaseStatus('Base común conectada · 0 lecturas · 0 equipos únicos', 'ok');
  };
})();
"""


def _install_service_order_patch() -> None:
    from . import service_order_page as module

    page_class = module.ServiceOrderPage
    if getattr(page_class, "_v1_0_24_50_patched", False):
        return

    original_init = page_class.__init__
    original_clear_form = page_class.clear_form
    original_save_record = page_class.save_record

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _make_service_actions_sticky(self)

    def patched_clear_form(self):
        original_clear_form(self)
        # A new order clears order-specific data, but not the operator's
        # preferred destination folder.
        self.output_folder.setText(self.last_output_folder or "")

    def patched_save_record(self):
        folder = self.output_folder.text().strip()
        if folder and Path(folder).is_dir():
            self._save_last_output_folder(folder)
        original_save_record(self)

    def patched_save_last_output_folder(self, folder: str) -> None:
        folder = str(folder or "").strip()
        if not folder:
            return
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            payload: dict = {}
            if self.settings_path.exists():
                try:
                    loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        payload.update(loaded)
                except (OSError, ValueError, TypeError):
                    pass
            payload["last_output_folder"] = folder
            self.settings_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.last_output_folder = folder
        except OSError:
            self.last_output_folder = folder

    page_class.__init__ = patched_init
    page_class.clear_form = patched_clear_form
    page_class.save_record = patched_save_record
    page_class._save_last_output_folder = patched_save_last_output_folder
    page_class._v1_0_24_50_patched = True


def _make_service_actions_sticky(page) -> None:
    """Move the five service-order actions below the scroll area.

    v1.0.24.49 creates the action row inside the form's QScrollArea. Reusing the
    same buttons in a fixed panel keeps their existing signal connections and
    behavior while making them permanently visible.
    """
    if getattr(page, "_service_sticky_actions_installed", False):
        return

    splitter = page.form_scroll.parentWidget()
    if not isinstance(splitter, QSplitter):
        return

    button_texts = (
        "Nuevo / limpiar",
        "Eliminar registro",
        "Guardar registro",
        "Vista previa de cédula",
        "Guardar y generar cédula",
    )
    buttons_by_text = {
        button.text(): button
        for button in page.findChildren(QPushButton)
        if button.text() in button_texts
    }
    if any(text not in buttons_by_text for text in button_texts):
        return

    original_index = splitter.indexOf(page.form_scroll)
    if original_index < 0:
        return

    panel = QWidget(splitter)
    panel.setObjectName("serviceOrderFormPanel")
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(0, 0, 0, 0)
    panel_layout.setSpacing(6)

    page.form_scroll.setParent(panel)
    panel_layout.addWidget(page.form_scroll, 1)

    sticky_host = QWidget(panel)
    sticky_host.setObjectName("serviceOrderStickyActions")
    sticky_layout = QHBoxLayout(sticky_host)
    sticky_layout.setContentsMargins(5, 6, 14, 5)

    sticky_layout.addWidget(buttons_by_text["Nuevo / limpiar"])
    sticky_layout.addStretch(1)
    sticky_layout.addWidget(buttons_by_text["Eliminar registro"])
    sticky_layout.addWidget(buttons_by_text["Guardar registro"])
    sticky_layout.addWidget(buttons_by_text["Vista previa de cédula"])
    sticky_layout.addWidget(buttons_by_text["Guardar y generar cédula"])
    panel_layout.addWidget(sticky_host, 0)

    splitter.insertWidget(original_index, panel)
    page._service_sticky_actions_installed = True
    page._service_sticky_actions_host = sticky_host


def _install_counter_history_patch() -> None:
    from . import counter_registry_page as module

    page_class = module.CounterRegistryPage
    if getattr(page_class, "_v1_0_24_50_patched", False):
        return

    original_init = page_class.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        def install_override(*_args):
            self.browser.page().runJavaScript(_HARD_CLEAR_HISTORY_JS)

        self.browser.loadFinished.connect(install_override)
        install_override()

    page_class.__init__ = patched_init
    page_class._v1_0_24_50_patched = True


def apply_patches() -> None:
    """Apply the v1.0.24.50 behavior changes on top of the exact v1.0.24.49 code."""
    _install_service_order_patch()
    _install_counter_history_patch()
