import multiprocessing
import controller
import view_ctk


def main():
    app_controller = controller.MeshAnalyzerController("projects.json")
    app_view = view_ctk.MeshAnalyzerView(app_controller)
    app_view.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
