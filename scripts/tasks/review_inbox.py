"""
Interactive CLI for reviewing AI File Organizer Proposals
Usage: python scripts/tasks/review_inbox.py
"""
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tasks.file_ai_organizer import get_all_proposals, apply_proposal, reject_proposal, approve_all_pending

def print_header():
    print("=" * 65)
    print("🤖 HomeServer: Интерактивное Согласование Входящих Файлов")
    print("=" * 65)

def main():
    print_header()
    proposals = get_all_proposals()
    pending = [p for p in proposals if p.get("status") == "pending"]
    
    if not pending:
        print("\n✨ Нет файлов, ожидающих решения. Все чисто!\n")
        return
        
    print(f"\nНайдено файлов на согласовании: {len(pending)}\n")
    
    for idx, p in enumerate(pending, 1):
        print(f"[{idx}/{len(pending)}] 📄 Файл: {p['file_name']} ({p['file_size_kb']} КБ)")
        print(f"    🤖 Резюме AI: {p['summary']}")
        print(f"    📂 Категория: {p['category']}")
        print(f"    🎯 Куда перенести: {p['suggested_destination']}")
        print(f"    🏷️ Теги: {', '.join(p.get('tags', []))}")
        print("    " + "-" * 55)
        
        while True:
            choice = input("    [Y] Согласиться / [E] Изменить путь / [R] Отклонить / [A] Принять все / [Q] Выход: ").strip().lower()
            if choice in ["y", "д", "yes", ""]:
                success = apply_proposal(p["id"])
                if success:
                    print("    ✅ Перемещено успешно!")
                else:
                    print("    ❌ Ошибка перемещения (исходный файл не найден)")
                break
            elif choice in ["e", "и", "edit"]:
                custom_dest = input("    Введите новый полный путь назначения: ").strip()
                if custom_dest:
                    success = apply_proposal(p["id"], custom_dest)
                    if success:
                        print(f"    ✅ Перемещено в: {custom_dest}")
                    else:
                        print("    ❌ Ошибка перемещения.")
                    break
            elif choice in ["r", "о", "reject"]:
                reject_proposal(p["id"])
                print("    🚫 Предложение отклонено (файл остался во входящих)")
                break
            elif choice in ["a", "все", "all"]:
                count = approve_all_pending()
                print(f"\n🎉 Все оставшиеся файлы ({count}) успешно согласованы и перемещены!\n")
                return
            elif choice in ["q", "й", "quit", "exit"]:
                print("\nВыход из программы согласования.\n")
                return
            else:
                print("    Неверный ввод. Попробуйте еще раз.")
        print()

    print("🎉 Обработка завершена!")

if __name__ == "__main__":
    main()
