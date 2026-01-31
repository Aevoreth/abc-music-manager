import flet as ft

def main(page: ft.Page):
    page.title = "ABC Music Manager"
    page.add(ft.Text("Hello, ABC Music Manager!"))

ft.app(target=main)
