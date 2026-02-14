# gui_utils/executor.py
import threading

from launcher import run_all, run_storytools_execution   # assumed to exist


class Executor:
    def __init__(self, status_bar):
        self.status_bar = status_bar

    def run_all_threaded(self, config_path, jobtype_list, only_sequence=None):
        if not only_sequence:
            self.status_bar.showMessage("No sequence selected", 5000)
            return

        def target():
            try:
                run_all(
                    config_path=str(config_path),
                    allowed_jobtypes=jobtype_list,
                    only_sequence=only_sequence
                )
                self.status_bar.showMessage("Execution completed", 5000)
            except Exception as e:
                self.status_bar.showMessage(f"Run failed: {str(e)}", 10000)

        threading.Thread(target=target, daemon=True).start()

    def run_selected_threaded(self, config, jobtype_list, target_sequence, target_shot):
        if not target_shot:
            return

        def target():
            try:
                run_storytools_execution(
                    config=config,
                    allowed_jobtypes=jobtype_list,
                    target_sequence=target_sequence,
                    target_shot=target_shot
                )
                self.status_bar.showMessage("Execution completed", 5000)
            except Exception as e:
                self.status_bar.showMessage(f"Run failed: {str(e)}", 10000)

        threading.Thread(target=target, daemon=True).start()