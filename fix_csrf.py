with open('templates/app_index.html', 'r') as f:
    content = f.read()

content = content.replace('window.csrfToken = "{{ csrf_token() }}";', 'window.csrfToken = "{{ session.get(\'csrf_token\', \'\') }}";')

with open('templates/app_index.html', 'w') as f:
    f.write(content)
