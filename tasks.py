from invoke.tasks import task

@task
def back(c):
    c.run("python app.py")


@task
def front(c):
    c.run("streamlit run ui.py")