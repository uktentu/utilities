import os
import shutil

def categorize_downloads_folder():
    # Define the Downloads folder path
    downloads_folder = os.path.expanduser("~/Downloads")
    
    # Check if Downloads folder exists
    if not os.path.exists(downloads_folder):
        print("Downloads folder not found.")
        return
    
    # Define categories and their associated file extensions
    categories = {
        "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".svg"],
        "Documents": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"],
        "Videos": [".mp4", ".mkv", ".mov", ".avi", ".flv", ".wmv"],
        "Audio": [".mp3", ".wav", ".aac", ".flac", ".ogg"],
        "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
        "Applications": [".dmg", ".pkg", ".app"],
        "Others": []  # For uncategorized files
    }
    
    # Create subfolders for each category
    for category in categories:
        category_folder = os.path.join(downloads_folder, category)
        os.makedirs(category_folder, exist_ok=True)
    
    # Iterate through files in the Downloads folder
    for file_name in os.listdir(downloads_folder):
        file_path = os.path.join(downloads_folder, file_name)
        
        # Skip directories and system files like .DS_Store
        if os.path.isdir(file_path) or file_name.startswith('.'):
            continue
        
        # Find the file's extension
        _, file_extension = os.path.splitext(file_name)
        
        # Find the category for the file
        destination_folder = None
        for category, extensions in categories.items():
            if file_extension.lower() in extensions:
                destination_folder = os.path.join(downloads_folder, category)
                break
        
        # If no specific category, put it in "Others"
        if not destination_folder:
            destination_folder = os.path.join(downloads_folder, "Others")
        
        # Move the file to the appropriate folder
        destination_path = os.path.join(destination_folder, file_name)
        
        try:
            shutil.move(file_path, destination_path)
            print(f"Moved: {file_name} -> {destination_folder}")
        except shutil.Error as e:
            print(f"Skipping {file_name}: {e}")

    print("File categorization completed.")

if __name__ == "__main__":
    categorize_downloads_folder()
