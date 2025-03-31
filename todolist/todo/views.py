import json
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import HttpResponse

from .models import Task
from .forms import TaskForm
from .google_calendar import (
    get_google_credentials, save_token, 
    create_google_event, update_google_event, delete_google_event
)

class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'todo/task_list.html'
    context_object_name = 'tasks'
    
    def get_queryset(self):
        return Task.objects.filter(user=self.request.user).order_by('-created_date')

class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    template_name = 'todo/task_detail.html'
    
    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'todo/task_form.html'
    success_url = reverse_lazy('task-list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        task = form.save()
        try:
            cred, auth_url = get_google_credentials(self.request)
            if cred:
                id = create_google_event(cred, task)
                task.google_event_id = id
                task.save()
            elif auth_url:
                self.request.session['pending_task_id'] = task.id
                return redirect('google-auth')
        except Exception as e:
            messages.warning(self.request, f"Task created but not synced to Google Calendar: {str(e)}")
        
        return super().form_valid(form)

class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'todo/task_form.html'
    success_url = reverse_lazy('task-list')
    
    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        task = form.save()
        try:
            creds, auth_url = get_google_credentials(self.request)
            if creds:
                event_id = update_google_event(creds, task)
                if not task.google_event_id:
                    task.google_event_id = event_id
                    task.save()
            elif auth_url:
                self.request.session['pending_task_id'] = task.id
                return redirect('google-auth')
        except Exception as e:
            messages.warning(self.request, f"Task updated but not synced to Google Calendar: {str(e)}")
        
        return super().form_valid(form)

class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    success_url = reverse_lazy('task-list')
    
    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)
    def delete(self, request, *args, **kwargs):
        task = self.get_object()
        try:
            creds, auth_url = get_google_credentials(self.request)
            if creds and task.google_event_id:
                delete_google_event(creds, task.google_event_id)
        except Exception as e:
            messages.warning(self.request, f"Task deleted but may still exist in Google Calendar: {str(e)}")
        
        return super().delete(request, *args, **kwargs)
    
@login_required
def task_complete(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    task.completed = not task.completed
    task.save()
    try:
        creds, auth_url = get_google_credentials(request)
        if creds and task.google_event_id:
            update_google_event(creds, task)
    except Exception as e:
        messages.warning(request, f"Task status updated but not synced to Google Calendar: {str(e)}")
    
    return redirect('task-list')

@login_required
def google_auth(request):
    creds, auth_url = get_google_credentials(request)
    if creds:
        return redirect('task-list')
    
    return render(request, 'todo/google_auth.html', {'auth_url': auth_url})

@login_required
def google_callback(request):
    if request.method == 'POST':
        auth_code = request.POST.get('auth_code')
        if not auth_code:
            messages.error(request, "Authorization code is required")
            return redirect('google-auth')
        
        try:
            creds = save_token(request.user.id, auth_code)
            pending_task_id = request.session.get('pending_task_id')
            if pending_task_id:
                task = get_object_or_404(Task, pk=pending_task_id, user=request.user)
                event_id = create_google_event(creds, task)
                task.google_event_id = event_id
                task.save()
                del request.session['pending_task_id']
            
            messages.success(request, "Successfully connected to Google Calendar")
        except Exception as e:
            messages.error(request, f"Error connecting to Google Calendar: {str(e)}")
        
        return redirect('task-list')
    
    return redirect('google-auth')