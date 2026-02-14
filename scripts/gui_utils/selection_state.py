# gui_utils/selection_state.py
from PySide6.QtWidgets import QLabel, QCheckBox
from PySide6.QtCore import Qt

from gui_utils.constants import JOBTYPE_HOST_MAPPING


class SelectionState:
    def __init__(self):
        self.selected_seq = None
        self.selected_shot = None
        self.selected_jobtype = None
        self.host_selections = {}
        self.host_checkboxes = []

    def clear_shot_selection(self):
        self.selected_seq = None
        self.selected_shot = None

    def set_from_single_shot(self, seq, shot, config, jobtype_combo):
        self.selected_seq = seq
        self.selected_shot = shot

        # Keep existing jobtype if already selected
        if self.selected_jobtype and self.selected_jobtype != "Select Jobtype":
            idx = jobtype_combo.findText(self.selected_jobtype)
            if idx >= 0:
                jobtype_combo.setCurrentIndex(idx)
            return

        # Auto-detect only if no jobtype chosen
        jobtypes = set()
        shot_data = config.get(config.get("project", ""), {}).get(seq, {}).get(shot, {})
        for sub in shot_data.values():
            for k in ['JOBTYPE', 'IMAGE_JOBTYPE', 'VIDEO_JOBTYPE']:
                if k in sub:
                    jts = [jt.strip() for jt in sub[k].split(',') if jt.strip()]
                    jobtypes.update(jts)

        if jobtypes:
            first_jt = sorted(jobtypes)[0]
            self.selected_jobtype = first_jt
            idx = jobtype_combo.findText(first_jt)
            if idx >= 0:
                jobtype_combo.setCurrentIndex(idx)
                return

        self.selected_jobtype = None
        jobtype_combo.setCurrentIndex(0)

    def on_jobtype_changed(self, text, jobtype_combo, tree_view=None):
        if text == "Select Jobtype":
            self.selected_jobtype = None
        else:
            self.selected_jobtype = text

        if tree_view is not None:
            tree_view.viewport().update()
            tree_view.updateGeometry()
            tree_view.repaint()

    def update_host_checkboxes(self, hosts_layout, globals_config, selected_jobtype):
        # Clear existing widgets completely
        while hosts_layout.count():
            item = hosts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.host_checkboxes.clear()

        if not selected_jobtype or selected_jobtype == "Select Jobtype":
            hosts_layout.addWidget(QLabel("No jobtype selected"))
            hosts_layout.addStretch()
            return

        host_key = JOBTYPE_HOST_MAPPING.get(selected_jobtype)
        if not host_key:
            hosts_layout.addWidget(QLabel("No host key for this jobtype"))
            hosts_layout.addStretch()
            return

        host_str = (
            globals_config.get(host_key + '_HOSTS', '') or
            globals_config.get(host_key, '')
        )
        hosts = [h.strip() for h in host_str.split(',') if h.strip()]

        if not hosts:
            hosts_layout.addWidget(QLabel("No hosts configured"))
            hosts_layout.addStretch()
            return

        if selected_jobtype not in self.host_selections:
            self.host_selections[selected_jobtype] = set(hosts)

        selected_hosts = self.host_selections[selected_jobtype]

        for host in hosts:
            cb = QCheckBox(host)
            cb.setChecked(host in selected_hosts)
            cb.stateChanged.connect(
                lambda state, h=host, jt=selected_jobtype: self._on_host_toggled(jt, h, bool(state))
            )
            hosts_layout.addWidget(cb)
            self.host_checkboxes.append((host, cb))

        hosts_layout.addStretch()

    def _on_host_toggled(self, jobtype, host, checked):
        s = self.host_selections.setdefault(jobtype, set())
        if checked:
            s.add(host)
        else:
            s.discard(host)

    def get_active_jobtype(self):
        return self.selected_jobtype or "ct_flux_t2i"

    def has_shot_selected(self):
        return bool(self.selected_shot)

    def has_sequence_selected(self):
        return bool(self.selected_seq)