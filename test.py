import requests
import pandas as pd
from decouple import config

# Configuración
API_URL = 'https://canvas.uautonoma.cl/api/v1'
ACCESS_TOKEN = config('TOKEN')  # Reemplaza con tu token de acceso
COURSE_ID = '57386'  # Reemplaza con tu ID de curso

# Encabezados para autenticación
headers = {
    'Authorization': f'Bearer {ACCESS_TOKEN}'
}

def main():
    # Obtener la lista de IDs y nombres de los estudiantes
    students = []
    url = f'{API_URL}/courses/{COURSE_ID}/students'
    params = {'per_page': 100}
    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        students.extend(response.json())
        url = response.links.get('next', {}).get('url')
    student_ids = [s['id'] for s in students if not s['name'] == 'Estudiante de prueba']
    student_names = {s['id']: s['name'] for s in students if not s['name'] == 'Estudiante de prueba'}

    # Obtener la lista de tareas (assignments) y sus nombres
    assignments = []
    url = f'{API_URL}/courses/{COURSE_ID}/assignments'
    params = {'per_page': 100}
    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        assignments.extend(response.json())
        url = response.links.get('next', {}).get('url')
    assignment_names = {a['id']: a['name'] for a in assignments}

    # Obtener las inscripciones para extraer las notas finales
    enrollments = []
    url = f'{API_URL}/courses/{COURSE_ID}/enrollments'
    params = {'type[]': 'StudentEnrollment', 'state[]': 'active', 'per_page': 100}
    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        enrollments.extend(response.json())
        url = response.links.get('next', {}).get('url')

    # Crear diccionarios con las notas finales de cada estudiante
    final_grades = {}
    final_scores = {}
    for enrollment in enrollments:
        user_id = enrollment['user_id']
        grades = enrollment.get('grades', {})
        final_grade = grades.get('final_grade', '-')  # Nota final en formato de letra
        final_score = grades.get('final_score', '-')  # Nota final en formato numérico
        final_grades[user_id] = final_grade
        final_scores[user_id] = final_score

    # Configurar los parámetros de la solicitud para las submissions
    url = f'{API_URL}/courses/{COURSE_ID}/students/submissions'
    params = {
        'include[]': 'sub_assignment_submissions',
        'exclude_response_fields[]': ['preview_url', 'external_tool_url', 'url'],
        'grouped': 1,
        'response_fields[]': [
            'assignment_id', 'attachments', 'attempt', 'cached_due_date',
            'custom_grade_status_id', 'entered_grade', 'entered_score',
            'excused', 'grade', 'grade_matches_current_submission',
            'grading_period_id', 'id', 'late', 'late_policy_status', 'missing',
            'points_deducted', 'posted_at', 'proxy_submitter',
            'proxy_submitter_id', 'redo_request', 'score', 'seconds_late',
            'sticker', 'submission_type', 'submitted_at', 'user_id',
            'workflow_state'
        ],
        'student_ids[]': student_ids,
        'per_page': 100
    }

    # Obtener las submissions
    submissions = []
    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        submissions.extend(response.json())
        url = response.links.get('next', {}).get('url')

    # Construir la tabla
    data = []
    for student in submissions:
        student_id = student['user_id']
        student_name = student_names.get(student_id, 'Desconocido')
        row = {'Estudiante': student_name}
        for submission in student['submissions']:
            assignment_id = submission['assignment_id']
            assignment_name = assignment_names.get(assignment_id, f'Tarea {assignment_id}')
            grade = submission.get('grade', '-')
            row[assignment_name] = grade
        # Agregar las notas finales al registro
        row['Nota'] = final_grades.get(student_id, '-')
        row['Puntaje'] = final_scores.get(student_id, '-')
        data.append(row)

    df = pd.DataFrame(data)
    df = df.set_index('Estudiante')
    # Ordenar los estudiantes de forma alfabética
    df = df.sort_index()
    print(df)

if __name__ == '__main__':
    main()